import asyncio
import logging

import discord

log = logging.getLogger(__name__)


class Jobs:
    def __init__(self, bot):
        self.bot, self.app = bot, bot.app
        self.task = None

    def start(self):
        self.task = asyncio.create_task(self.run(), name="gumabot-jobs")

    async def tick(self):
        for operation in (
            self.app.grading.complete_due,
            self.app.auctions.settle_due,
            self.app.trades.expire,
            self.app.claims.expire,
            self.app.gameplay.expire,
            self.app.progression.rollover,
            self.process_votes,
            self.reminders,
        ):
            try:
                await operation()
            except Exception:
                log.exception("Background job failed: %s", operation.__name__)

    async def process_votes(self):
        from ..services.errors import DomainError, ProviderUnavailable

        async with self.app.db.read() as tx:
            votes = await tx.all(
                "SELECT * FROM vote_inbox WHERE status='pending' ORDER BY received_at LIMIT 10"
            )
        for vote in votes:
            try:
                await self.app.economy.verified_vote(
                    vote["user_id"], vote["id"], self.app.settings.featured_set
                )
                status = "completed"
            except ProviderUnavailable:
                continue
            except DomainError:
                status = "ignored"
            async with self.app.db.transaction() as tx:
                await tx.execute(
                    "UPDATE vote_inbox SET status=:s WHERE id=:id AND status='pending'",
                    s=status,
                    id=vote["id"],
                )

    async def run(self):
        await self.bot.wait_until_ready()
        try:
            await self.app.provider.list_sets()
        except Exception:
            log.warning("Initial set-list refresh failed; lazy sync remains available")
        while True:
            await self.tick()
            await asyncio.sleep(45)

    async def reminders(self):
        now = self.app.clock.timestamp()
        async with self.app.db.read() as tx:
            rows = await tx.all(
                "SELECT * FROM reminder_preferences WHERE enabled=1 AND last_sent<:t LIMIT 100",
                t=now - 3600,
            )
        for row in rows:
            async with self.app.db.read() as tx:
                if row["kind"] == "energy":
                    user = await self.app.cards.user(tx, row["user_id"])
                    due = user["energy_updated_at"] + max(0, 3 - user["energy"]) * 7200
                elif row["kind"] == "grading":
                    value = await tx.one(
                        "SELECT MAX(completed_at) AS due FROM grading_jobs WHERE user_id=:u AND completed_at>:last",
                        u=row["user_id"],
                        last=row["last_sent"],
                    )
                    due = value["due"]
                elif row["kind"] == "auction":
                    value = await tx.one(
                        "SELECT MAX(due_at) AS due FROM auctions WHERE (seller=:u OR bidder=:u) AND status='completed' AND due_at>:last",
                        u=row["user_id"],
                        last=row["last_sent"],
                    )
                    due = value["due"]
                else:
                    value = await tx.one(
                        "SELECT due_at AS due FROM cooldowns WHERE user_id=:u AND kind=:k",
                        u=row["user_id"],
                        k=row["kind"],
                    )
                    due = value["due"] if value else None
            if due is None or due > now or due <= row["last_sent"]:
                continue
            # Claim delivery before networking: bounded at-most-once notification attempts.
            async with self.app.db.transaction() as tx:
                result = await tx.execute(
                    "UPDATE reminder_preferences SET last_sent=:t WHERE user_id=:u AND kind=:k AND last_sent=:old AND enabled=1",
                    t=now,
                    u=row["user_id"],
                    k=row["kind"],
                    old=row["last_sent"],
                )
            if not result.rowcount:
                continue
            try:
                user = self.bot.get_user(row["user_id"]) or await self.bot.fetch_user(
                    row["user_id"]
                )
                await user.send(
                    f"GumaBot reminder: {row['kind']} is ready.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                log.info("Reminder delivery unavailable for user %s", row["user_id"])

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
