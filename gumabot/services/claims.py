from .core import Service
from .errors import AlreadyClaimed, DomainError


class Claims(Service):
    def __init__(self, db, clock, cards, rng=None):
        super().__init__(db, clock, rng)
        self.cards = cards

    async def peek(self, uid, code):
        async with self.db.transaction() as tx:
            card = await self.available(tx, uid, code)
            count = await tx.one(
                "SELECT COUNT(*) AS n FROM owned_cards WHERE owner_id=:u AND catalog_card_id=:c AND locked_reason IS NULL",
                u=uid,
                c=card["catalog_card_id"],
            )
            if count["n"] < 2:
                raise DomainError("Pack Peek requires a spare duplicate.")
            key = self.identifier()
            await tx.execute(
                "UPDATE owned_cards SET locked_reason='peek' WHERE id=:c", c=card["id"]
            )
            await tx.execute(
                "INSERT INTO pack_peek_offers VALUES (:id,:c,:u,:due,'active')",
                id=key,
                c=card["id"],
                u=uid,
                due=self.now() + 600,
            )
            return key

    async def claim_peek(self, uid, key):
        async with self.db.transaction() as tx:
            await self.user(tx, uid)
            offer = await tx.one(
                "SELECT * FROM pack_peek_offers WHERE id=:id AND status='active' AND due_at>:t",
                id=key,
                t=self.now(),
            )
            if not offer:
                raise AlreadyClaimed()
            if offer["owner_id"] == uid:
                raise DomainError("Another player must claim this card.")
            await tx.execute(
                "UPDATE pack_peek_offers SET status='claimed' WHERE id=:id AND status='active'",
                id=key,
            )
            await tx.execute(
                "INSERT INTO pack_peek_claims VALUES (:id,:u,:t)", id=key, u=uid, t=self.now()
            )
            await tx.execute("DELETE FROM deck_cards WHERE card_id=:c", c=offer["card_id"])
            await tx.execute(
                "UPDATE owned_cards SET owner_id=:u,locked_reason=NULL WHERE id=:c",
                u=uid,
                c=offer["card_id"],
            )
            await self.transferred(tx, uid, offer["card_id"])
            await self.money(tx, offer["owner_id"], 10, "PEEK", key)

    async def create_drop(self, guild, catalog):
        async with self.db.transaction() as tx:
            row = await tx.one("SELECT * FROM guilds WHERE id=:g", g=guild)
            if not row or not row["drop_enabled"] or row["last_drop_at"] > self.now() - 3600:
                raise DomainError("Drops are unavailable or on cooldown.")
            key = self.identifier()
            await tx.execute(
                "UPDATE guilds SET last_drop_at=:t,activity=0 WHERE id=:g", t=self.now(), g=guild
            )
            await tx.execute(
                "INSERT INTO server_drops VALUES (:id,:g,:c,:due,NULL,:t)",
                id=key,
                g=guild,
                c=catalog,
                due=self.now() + 600,
                t=self.now(),
            )
            return key

    async def claim_drop(self, uid, key, guild):
        async with self.db.transaction() as tx:
            await self.user(tx, uid)
            row = await tx.one(
                "SELECT * FROM server_drops WHERE id=:id AND guild_id=:g AND claimant IS NULL AND due_at>:t",
                id=key,
                g=guild,
                t=self.now(),
            )
            if not row:
                raise AlreadyClaimed()
            await tx.execute(
                "UPDATE server_drops SET claimant=:u WHERE id=:id AND claimant IS NULL",
                u=uid,
                id=key,
            )
            return await self.cards.mint(tx, uid, row["card_id"], "server_drop")

    async def expire(self):
        async with self.db.transaction() as tx:
            offers = await tx.all(
                "SELECT * FROM pack_peek_offers WHERE status='active' AND due_at<=:t LIMIT 100",
                t=self.now(),
            )
            for offer in offers:
                await tx.execute(
                    "UPDATE owned_cards SET locked_reason=NULL WHERE id=:c AND locked_reason='peek'",
                    c=offer["card_id"],
                )
                await tx.execute(
                    "UPDATE pack_peek_offers SET status='expired' WHERE id=:id", id=offer["id"]
                )
