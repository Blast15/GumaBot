import json
import random
import secrets
from datetime import datetime, timezone

from .errors import CardLocked, CardNotOwned, CooldownActive, DomainError, InsufficientFunds
from .rules import energy, level_for


class Service:
    def __init__(self, db, clock, rng=None):
        self.db, self.clock = db, clock
        self.rng = rng or random.Random()

    def now(self):
        return self.clock.timestamp()

    @staticmethod
    def identifier():
        return secrets.token_hex(8)

    @staticmethod
    def positive(value, maximum=1_000_000):
        if type(value) is not int or not 1 <= value <= maximum:
            raise DomainError(f"Amount must be an integer between 1 and {maximum}.")

    async def user(self, tx, uid):
        row = await tx.one("SELECT * FROM users WHERE discord_user_id=:u", u=uid)
        if not row:
            raise DomainError("Run /start first.")
        return row

    async def money(self, tx, uid, delta, reason, correlation, currency="coins"):
        if currency not in ("coins", "aura") or type(delta) is not int:
            raise ValueError("Invalid ledger entry")
        result = await tx.execute(
            f"UPDATE users SET {currency}={currency}+:d WHERE discord_user_id=:u AND {currency}+:d>=0 AND {currency}+:d<=9000000000000000",
            d=delta,
            u=uid,
        )
        if result.rowcount != 1:
            raise InsufficientFunds()
        await tx.execute(
            "INSERT INTO currency_ledger (user_id,currency,amount_delta,reason,correlation_id,created_at) VALUES (:u,:c,:d,:r,:id,:now)",
            u=uid,
            c=currency,
            d=delta,
            r=reason,
            id=correlation,
            now=self.now(),
        )

    async def available(self, tx, uid, code):
        card = await tx.one("SELECT * FROM owned_cards WHERE public_code=:code", code=code.upper())
        if not card or card["owner_id"] != uid:
            raise CardNotOwned()
        if card["locked_reason"]:
            raise CardLocked()
        return card

    async def cooldown(self, tx, uid, kind, interval):
        await self.user(tx, uid)
        row = await tx.one(
            "SELECT due_at FROM cooldowns WHERE user_id=:u AND kind=:k", u=uid, k=kind
        )
        if row and row["due_at"] > self.now():
            raise CooldownActive(row["due_at"])
        await tx.execute(
            "INSERT INTO cooldowns VALUES (:u,:k,:due) ON CONFLICT(user_id,kind) DO UPDATE SET due_at=excluded.due_at",
            u=uid,
            k=kind,
            due=self.now() + interval,
        )

    async def item(self, tx, uid, key, delta):
        if delta > 0:
            await tx.execute(
                "INSERT INTO user_items VALUES (:u,:k,:d) ON CONFLICT(user_id,item_id) DO UPDATE SET quantity=quantity+:d",
                u=uid,
                k=key,
                d=delta,
            )
        else:
            result = await tx.execute(
                "UPDATE user_items SET quantity=quantity+:d WHERE user_id=:u AND item_id=:k AND quantity>=-:d",
                u=uid,
                k=key,
                d=delta,
            )
            if result.rowcount != 1:
                raise DomainError("You do not have that item.")

    async def refresh_energy(self, tx, uid):
        user = await self.user(tx, uid)
        value, updated = energy(user["energy"], user["energy_updated_at"], self.now())
        await tx.execute(
            "UPDATE users SET energy=:e,energy_updated_at=:t WHERE discord_user_id=:u",
            e=value,
            t=updated,
            u=uid,
        )
        return value

    async def add_energy(self, tx, uid, delta, reason):
        await self.refresh_energy(tx, uid)
        await tx.execute(
            "UPDATE users SET energy=energy+:d WHERE discord_user_id=:u", d=delta, u=uid
        )
        await tx.execute(
            "INSERT INTO energy_events(user_id,delta,reason,created_at) VALUES (:u,:d,:r,:t)",
            u=uid,
            d=delta,
            r=reason,
            t=self.now(),
        )

    async def receipt(self, tx, uid, key, kind):
        row = await tx.one("SELECT * FROM action_receipts WHERE id=:id", id=key)
        if row:
            if row["user_id"] != uid or row["kind"] != kind:
                raise DomainError("Invalid interaction reference.")
            return json.loads(row["payload"])

    async def save_receipt(self, tx, uid, key, kind, payload):
        await tx.execute(
            "INSERT INTO action_receipts VALUES (:id,:u,:k,:p)",
            id=key,
            u=uid,
            k=kind,
            p=json.dumps(payload),
        )

    async def event(self, tx, uid, event, xp=10):
        user = await self.user(tx, uid)
        new_xp = user["xp"] + xp
        level = level_for(new_xp)
        await tx.execute(
            "UPDATE users SET xp=:xp,level=:level WHERE discord_user_id=:u",
            xp=new_xp,
            level=level,
            u=uid,
        )
        rewards = await tx.all(
            "SELECT * FROM level_rewards WHERE level>:old AND level<=:new",
            old=user["level"],
            new=level,
        )
        for reward in rewards:
            for currency in ("coins", "aura"):
                await self.money(
                    tx, uid, reward[currency], "LEVEL", f"level:{uid}:{reward['level']}", currency
                )
        if event != "level":
            for _ in rewards:
                await self.event(tx, uid, "level", 0)
        day = self.clock.now().date().isoformat()
        quests = await tx.all("SELECT * FROM quests ORDER BY id")
        # Stable rotation gives everyone exactly three daily objectives without remote state.
        offset = self.clock.now().date().toordinal() % len(quests)
        for quest in (quests * 2)[offset : offset + 3]:
            await tx.execute(
                "INSERT INTO user_quests(user_id,day,quest_id) VALUES (:u,:day,:q) ON CONFLICT DO NOTHING",
                u=uid,
                day=day,
                q=quest["id"],
            )
            if quest["event"] == event:
                await tx.execute(
                    "UPDATE user_quests SET progress=MIN(progress+1,:target) WHERE user_id=:u AND day=:day AND quest_id=:q",
                    target=quest["target"],
                    u=uid,
                    day=day,
                    q=quest["id"],
                )
                result = await tx.execute(
                    "UPDATE user_quests SET claimed=1 WHERE user_id=:u AND day=:day AND quest_id=:q AND progress>=:target AND claimed=0",
                    target=quest["target"],
                    u=uid,
                    day=day,
                    q=quest["id"],
                )
                if result.rowcount:
                    await self.money(
                        tx, uid, quest["reward"], "QUEST", f"{day}:{uid}:{quest['id']}"
                    )
        for achievement in await tx.all("SELECT * FROM achievements WHERE event=:e", e=event):
            await tx.execute(
                "INSERT INTO user_achievements VALUES (:u,:a,1,0) ON CONFLICT(user_id,achievement_id) DO UPDATE SET progress=progress+1",
                u=uid,
                a=achievement["id"],
            )
            result = await tx.execute(
                "UPDATE user_achievements SET awarded=1 WHERE user_id=:u AND achievement_id=:a AND progress>=:t AND awarded=0",
                u=uid,
                a=achievement["id"],
                t=achievement["target"],
            )
            if result.rowcount:
                await self.money(
                    tx, uid, achievement["reward"], "ACHIEVEMENT", f"{uid}:{achievement['id']}"
                )
        now = self.clock.now()
        season = now.strftime("%Y-%m")
        end = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=timezone.utc)
        await tx.execute(
            "INSERT INTO seasons VALUES (:id,:end,0) ON CONFLICT DO NOTHING",
            id=season,
            end=int(end.timestamp()),
        )
        await tx.execute(
            "INSERT INTO season_stats VALUES (:s,:u,:p) ON CONFLICT(season_id,user_id) DO UPDATE SET points=points+:p",
            s=season,
            u=uid,
            p=xp,
        )

    async def milestones(self, tx, uid, set_id):
        stats = await tx.one(
            "SELECT COUNT(DISTINCT o.catalog_card_id) AS owned,s.total FROM card_sets s LEFT JOIN card_catalog c ON c.set_id=s.id LEFT JOIN owned_cards o ON o.catalog_card_id=c.id AND o.owner_id=:u AND (o.locked_reason IS NULL OR o.locked_reason NOT IN ('fusion_consumed','sold_system')) WHERE s.id=:s GROUP BY s.id",
            u=uid,
            s=set_id,
        )
        if not stats or not stats["total"]:
            return
        for milestone in (25, 50, 75, 100):
            if stats["owned"] * 100 >= stats["total"] * milestone:
                result = await tx.execute(
                    "INSERT INTO set_milestones VALUES (:u,:s,:m) ON CONFLICT DO NOTHING",
                    u=uid,
                    s=set_id,
                    m=milestone,
                )
                if result.rowcount:
                    await self.money(
                        tx, uid, milestone, "SET_COMPLETION", f"{uid}:{set_id}:{milestone}"
                    )

    async def acquired(self, tx, uid, catalog):
        await self.event(tx, uid, "collection", 0)
        card = await tx.one("SELECT set_id FROM card_catalog WHERE id=:c", c=catalog)
        await self.milestones(tx, uid, card["set_id"])

    async def transferred(self, tx, uid, card_id):
        card = await tx.one("SELECT catalog_card_id FROM owned_cards WHERE id=:c", c=card_id)
        await self.acquired(tx, uid, card["catalog_card_id"])
