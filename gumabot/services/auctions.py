from ..utils.audit import audited
from .core import Service
from .errors import AuctionEnded, DomainError


class Auctions(Service):
    async def create(self, uid, code, price, hours=24, increment=5, buyout=None):
        self.positive(price)
        self.positive(increment)
        self.positive(hours, 168)
        if buyout is not None:
            self.positive(buyout)
            if buyout < price:
                raise DomainError("Buyout must be at least the start price.")
        async with self.db.transaction() as tx:
            card = await self.available(tx, uid, code)
            key = self.identifier()
            await tx.execute(
                "UPDATE owned_cards SET locked_reason='auction' WHERE id=:id", id=card["id"]
            )
            await tx.execute(
                "INSERT INTO auctions(id,seller,card_id,start_price,increment,buyout,due_at) VALUES (:id,:u,:c,:p,:inc,:b,:due)",
                id=key,
                u=uid,
                c=card["id"],
                p=price,
                inc=increment,
                b=buyout,
                due=self.now() + hours * 3600,
            )
            return key

    @audited
    async def bid(self, uid, key, amount):
        self.positive(amount)
        async with self.db.transaction() as tx:
            auction = await tx.one("SELECT * FROM auctions WHERE id=:id", id=key)
            if not auction or auction["status"] != "active" or auction["due_at"] <= self.now():
                raise AuctionEnded()
            if auction["seller"] == uid:
                raise DomainError("You cannot bid on your own auction.")
            minimum = (
                auction["current_bid"] + auction["increment"]
                if auction["bidder"]
                else auction["start_price"]
            )
            if amount < minimum:
                raise DomainError(f"Minimum bid: {minimum} coins.")
            if auction["buyout"]:
                amount = min(amount, auction["buyout"])
            if auction["bidder"]:
                await self.money(
                    tx, auction["bidder"], auction["current_bid"], "AUCTION_RELEASE", key
                )
            await self.money(tx, uid, -amount, "AUCTION_HOLD", key)
            await tx.execute(
                "INSERT INTO auction_holds VALUES (:id,:u,:a) ON CONFLICT(auction_id) DO UPDATE SET user_id=:u,amount=:a",
                id=key,
                u=uid,
                a=amount,
            )
            await tx.execute(
                "INSERT INTO auction_bids(auction_id,user_id,amount,created_at) VALUES (:id,:u,:a,:t)",
                id=key,
                u=uid,
                a=amount,
                t=self.now(),
            )
            await tx.execute(
                "UPDATE auctions SET bidder=:u,current_bid=:a,due_at=:due WHERE id=:id",
                u=uid,
                a=amount,
                due=self.now()
                if auction["buyout"] and amount >= auction["buyout"]
                else auction["due_at"],
                id=key,
            )
        await self.settle_due()

    @audited
    async def settle_due(self):
        async with self.db.transaction() as tx:
            rows = await tx.all(
                "SELECT * FROM auctions WHERE status='active' AND due_at<=:t LIMIT 100",
                t=self.now(),
            )
            for auction in rows:
                key = auction["id"]
                result = await tx.execute(
                    "UPDATE auctions SET status='completed' WHERE id=:id AND status='active'",
                    id=key,
                )
                if not result.rowcount:
                    continue
                if auction["bidder"]:
                    await self.money(
                        tx, auction["seller"], auction["current_bid"], "AUCTION_SETTLEMENT", key
                    )
                    await tx.execute(
                        "DELETE FROM deck_cards WHERE card_id=:c", c=auction["card_id"]
                    )
                    await tx.execute(
                        "UPDATE owned_cards SET owner_id=:u WHERE id=:c",
                        u=auction["bidder"],
                        c=auction["card_id"],
                    )
                    await tx.execute(
                        "INSERT INTO price_history(catalog_card_id,price,source,reference,created_at) SELECT catalog_card_id,:p,'auction',:id,:t FROM owned_cards WHERE id=:c",
                        p=auction["current_bid"],
                        id=key,
                        t=self.now(),
                        c=auction["card_id"],
                    )
                    await tx.execute("DELETE FROM auction_holds WHERE auction_id=:id", id=key)
                await tx.execute(
                    "UPDATE owned_cards SET locked_reason=NULL WHERE id=:c", c=auction["card_id"]
                )
            return len(rows)

    async def cancel(self, uid, key):
        async with self.db.transaction() as tx:
            row = await tx.one(
                "SELECT * FROM auctions WHERE id=:id AND seller=:u AND bidder IS NULL AND status='active' AND due_at>:t",
                id=key,
                u=uid,
                t=self.now(),
            )
            if not row:
                raise DomainError(
                    "Only an active auction with no bids can be cancelled by its seller."
                )
            await tx.execute("UPDATE auctions SET status='cancelled' WHERE id=:id", id=key)
            await tx.execute(
                "UPDATE owned_cards SET locked_reason=NULL WHERE id=:c", c=row["card_id"]
            )
