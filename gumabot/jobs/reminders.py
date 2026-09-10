"""Durable, bounded at-least-once delivery; Discord DMs have no idempotency key."""

import asyncio
import logging
import secrets

import discord

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 5
LEASE_SECONDS = 120


class Reminders:
    def __init__(self, bot):
        self.bot, self.app = bot, bot.app

    async def enqueue(self):
        now = self.app.clock.timestamp()
        async with self.app.db.transaction() as tx:
            rows = await tx.all(
                "SELECT * FROM reminder_preferences WHERE enabled=1 AND next_check_at<=:t "
                "AND last_sent<:cutoff ORDER BY next_check_at,user_id,kind LIMIT 100",
                t=now,
                cutoff=now - 3600,
            )
            for row in rows:
                uid, kind = row["user_id"], row["kind"]
                # Rotate even non-due rows so the first page cannot starve later users.
                await tx.execute(
                    "UPDATE reminder_preferences SET next_check_at=:t WHERE user_id=:u AND kind=:k",
                    t=now + 60,
                    u=uid,
                    k=kind,
                )
                if kind == "energy":
                    user = await self.app.cards.user(tx, uid)
                    due = user["energy_updated_at"] + max(0, 3 - user["energy"]) * 7200
                elif kind == "grading":
                    value = await tx.one(
                        "SELECT MAX(completed_at) AS due FROM grading_jobs WHERE user_id=:u AND completed_at>:last",
                        u=uid,
                        last=row["last_sent"],
                    )
                    due = value["due"]
                elif kind == "auction":
                    value = await tx.one(
                        "SELECT MAX(due_at) AS due FROM auctions WHERE (seller=:u OR bidder=:u) AND status='completed' AND due_at>:last",
                        u=uid,
                        last=row["last_sent"],
                    )
                    due = value["due"]
                else:
                    value = await tx.one(
                        "SELECT due_at AS due FROM cooldowns WHERE user_id=:u AND kind=:k",
                        u=uid,
                        k=kind,
                    )
                    due = value["due"] if value else None
                if due is None or due > now or due <= row["last_sent"]:
                    continue
                # One row per preference bounds storage; failed events are not retried forever.
                await tx.execute(
                    "INSERT INTO reminder_deliveries(user_id,kind,due_at,status,next_attempt_at) "
                    "VALUES (:u,:k,:due,'pending',:t) ON CONFLICT(user_id,kind) DO UPDATE SET "
                    "due_at=:due,status='pending',attempts=0,next_attempt_at=:t,claim_token=NULL "
                    "WHERE reminder_deliveries.status IN ('sent','failed') AND reminder_deliveries.due_at<:due",
                    u=uid,
                    k=kind,
                    due=due,
                    t=now,
                )

    async def run(self):
        await self.enqueue()
        now = self.app.clock.timestamp()
        async with self.app.db.transaction() as tx:
            await tx.execute(
                "UPDATE reminder_deliveries SET status='failed',claim_token=NULL "
                "WHERE status='claimed' AND next_attempt_at<=:t AND attempts>=:maximum",
                t=now,
                maximum=MAX_ATTEMPTS,
            )
            rows = await tx.all(
                "SELECT d.* FROM reminder_deliveries d JOIN reminder_preferences p USING(user_id,kind) "
                "WHERE p.enabled=1 AND d.status IN ('pending','claimed') AND d.next_attempt_at<=:t "
                "AND d.attempts<:maximum ORDER BY d.next_attempt_at,d.user_id,d.kind LIMIT 100",
                t=now,
                maximum=MAX_ATTEMPTS,
            )
        for row in rows:
            token = secrets.token_hex(16)
            now = self.app.clock.timestamp()
            async with self.app.db.transaction() as tx:
                result = await tx.execute(
                    "UPDATE reminder_deliveries SET status='claimed',attempts=attempts+1,"
                    "next_attempt_at=:lease,claim_token=:token WHERE user_id=:u AND kind=:k "
                    "AND status IN ('pending','claimed') AND next_attempt_at<=:t AND attempts<:maximum "
                    "AND EXISTS(SELECT 1 FROM reminder_preferences p WHERE p.user_id=:u AND p.kind=:k AND p.enabled=1)",
                    u=row["user_id"],
                    k=row["kind"],
                    lease=now + LEASE_SECONDS,
                    token=token,
                    t=now,
                    maximum=MAX_ATTEMPTS,
                )
            if not result.rowcount:
                continue
            try:
                async with asyncio.timeout(30):
                    user = self.bot.get_user(row["user_id"]) or await self.bot.fetch_user(
                        row["user_id"]
                    )
                    await user.send(
                        f"GumaBot reminder: {row['kind']} is ready.",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
            except Exception as exc:
                terminal = (
                    isinstance(exc, (discord.Forbidden, discord.NotFound))
                    or row["attempts"] + 1 >= MAX_ATTEMPTS
                )
                delay = min(3600, 60 * 2 ** row["attempts"])
                async with self.app.db.transaction() as tx:
                    await tx.execute(
                        "UPDATE reminder_deliveries SET status=:s,next_attempt_at=:t,claim_token=NULL "
                        "WHERE user_id=:u AND kind=:k AND claim_token=:token",
                        s="failed" if terminal else "pending",
                        t=self.app.clock.timestamp() + delay,
                        u=row["user_id"],
                        k=row["kind"],
                        token=token,
                    )
                log.warning(
                    "Reminder delivery failed",
                    extra={
                        "event": "reminder_failure",
                        "kind": row["kind"],
                        "attempt": row["attempts"] + 1,
                        "terminal": terminal,
                        "error_type": type(exc).__name__,
                    },
                )
            else:
                async with self.app.db.transaction() as tx:
                    result = await tx.execute(
                        "UPDATE reminder_deliveries SET status='sent',claim_token=NULL "
                        "WHERE user_id=:u AND kind=:k AND claim_token=:token",
                        u=row["user_id"],
                        k=row["kind"],
                        token=token,
                    )
                    if result.rowcount:
                        await tx.execute(
                            "UPDATE reminder_preferences SET last_sent=MAX(last_sent,:due) WHERE user_id=:u AND kind=:k",
                            due=row["due_at"],
                            u=row["user_id"],
                            k=row["kind"],
                        )
