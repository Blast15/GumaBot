from ..utils.audit import audited
from .core import Service
from .errors import DomainError


class Economy(Service):
    def __init__(self, db, clock, cards, rng=None):
        super().__init__(db, clock, rng)
        self.cards = cards

    async def balance(self, uid):
        async with self.db.transaction() as tx:
            await self.refresh_energy(tx, uid)
            return await self.user(tx, uid)

    @audited
    async def daily(self, uid):
        async with self.db.transaction() as tx:
            await self.cooldown(tx, uid, "daily", 86400)
            await self.money(tx, uid, 100, "DAILY", f"daily:{uid}:{self.now()}")
            await self.event(tx, uid, "daily", 10)
            return 100

    async def buy_item(self, uid, item, quantity, key):
        self.positive(quantity, 100)
        async with self.db.transaction() as tx:
            if await self.receipt(tx, uid, key, "item"):
                return
            row = await tx.one("SELECT * FROM shop_items WHERE id=:id", id=item)
            if not row:
                raise DomainError("Unknown item.")
            await self.money(tx, uid, -row["price"] * quantity, "ITEM_PURCHASE", key)
            await self.item(tx, uid, item, quantity)
            await self.save_receipt(tx, uid, key, "item", {"ok": True})

    async def buy_pack(self, uid, key):
        async with self.db.transaction() as tx:
            if await self.receipt(tx, uid, key, "energy"):
                return
            await self.money(tx, uid, -40, "PACK_PURCHASE", key)
            await self.add_energy(tx, uid, 1, "PACK_PURCHASE")
            await self.save_receipt(tx, uid, key, "energy", {"ok": True})

    async def give(self, uid, recipient, amount, code, key):
        if uid == recipient:
            raise DomainError("You cannot give to yourself.")
        if not code:
            self.positive(amount)
        async with self.db.transaction() as tx:
            if await self.receipt(tx, uid, key, "give"):
                return
            await self.user(tx, recipient)
            if code:
                card = await self.available(tx, uid, code)
                await tx.execute("DELETE FROM deck_cards WHERE card_id=:id", id=card["id"])
                await tx.execute(
                    "UPDATE owned_cards SET owner_id=:u WHERE id=:id", u=recipient, id=card["id"]
                )
                await self.transferred(tx, recipient, card["id"])
            else:
                await self.money(tx, uid, -amount, "GIVE", key)
                await self.money(tx, recipient, amount, "GIVE", key)
            await self.save_receipt(tx, uid, key, "give", {"ok": True})

    async def mystery_box(self, uid, set_id, key):
        pool = await self.cards.ensure_set(set_id)
        async with self.db.transaction() as tx:
            old = await self.receipt(tx, uid, key, "box")
            if old:
                return old
            await self.item(tx, uid, "box", -1)
            outcome = self.rng.choices(["coins", "aura", "card", "item"], [0.45, 0.2, 0.25, 0.1])[0]
            if outcome in ("coins", "aura"):
                amount = (
                    self.rng.randint(20, 100) if outcome == "coins" else self.rng.randint(1, 10)
                )
                await self.money(tx, uid, amount, "MYSTERY_BOX", key, outcome)
                result = {outcome: amount}
            elif outcome == "card":
                card = self.rng.choice(pool)
                result = {"card": await self.cards.mint(tx, uid, card["id"], "box")}
            else:
                await self.item(tx, uid, "tint", 1)
                result = {"item": "tint"}
            await self.save_receipt(tx, uid, key, "box", result)
            return result

    async def use_item(self, uid, item, key):
        if item not in ("booster", "cosmetic"):
            raise DomainError("Use /tint, /grade coupon:true or /mysterybox for that item.")
        async with self.db.transaction() as tx:
            if await self.receipt(tx, uid, key, "use_item"):
                return
            await self.item(tx, uid, item, -1)
            if item == "booster":
                await self.add_energy(tx, uid, 1, "BOOSTER")
            else:
                await tx.execute(
                    "UPDATE users SET trainer_avatar=REPLACE(trainer_avatar,' ★','') || ' ★' WHERE discord_user_id=:u",
                    u=uid,
                )
            await self.save_receipt(tx, uid, key, "use_item", {"ok": True})
