from statistics import median

from ..utils.audit import audited
from .core import Service
from .errors import DomainError, ListingUnavailable


class Market(Service):
    async def list_card(self, uid, code, price):
        self.positive(price)
        async with self.db.transaction() as tx:
            card = await self.available(tx, uid, code)
            key = self.identifier()
            await tx.execute(
                "UPDATE owned_cards SET locked_reason='market' WHERE id=:id", id=card["id"]
            )
            await tx.execute(
                "INSERT INTO market_listings VALUES (:id,:u,:c,:p,'active',:t)",
                id=key,
                u=uid,
                c=card["id"],
                p=price,
                t=self.now(),
            )
            return key

    async def browse(self, page=0):
        if not 0 <= page <= 100000:
            raise DomainError("Invalid page.")
        async with self.db.read() as tx:
            return await tx.all(
                "SELECT m.id,m.price,c.name,o.public_code FROM market_listings m JOIN owned_cards o ON m.card_id=o.id JOIN card_catalog c ON c.id=o.catalog_card_id WHERE m.status='active' ORDER BY m.created_at DESC,m.id LIMIT 10 OFFSET :offset",
                offset=page * 10,
            )

    @audited
    async def buy(self, uid, key):
        async with self.db.transaction() as tx:
            listing = await tx.one(
                "SELECT * FROM market_listings WHERE id=:id AND status='active'", id=key
            )
            if not listing:
                raise ListingUnavailable()
            if listing["seller"] == uid:
                raise DomainError("You cannot buy your own listing.")
            result = await tx.execute(
                "UPDATE market_listings SET status='sold' WHERE id=:id AND status='active'", id=key
            )
            if result.rowcount != 1:
                raise ListingUnavailable()
            await self.money(tx, uid, -listing["price"], "MARKET_PURCHASE", key)
            await self.money(tx, listing["seller"], listing["price"], "MARKET_SALE", key)
            await tx.execute("DELETE FROM deck_cards WHERE card_id=:c", c=listing["card_id"])
            await tx.execute(
                "UPDATE owned_cards SET owner_id=:u,locked_reason=NULL WHERE id=:c",
                u=uid,
                c=listing["card_id"],
            )
            await tx.execute(
                "INSERT INTO market_sales VALUES (:id,:u,:s,:p,:t)",
                id=key,
                u=uid,
                s=listing["seller"],
                p=listing["price"],
                t=self.now(),
            )
            await tx.execute(
                "INSERT INTO price_history(catalog_card_id,price,source,reference,created_at) SELECT catalog_card_id,:p,'market',:id,:t FROM owned_cards WHERE id=:c",
                p=listing["price"],
                id=key,
                t=self.now(),
                c=listing["card_id"],
            )
            await self.transferred(tx, uid, listing["card_id"])
            await self.event(tx, uid, "market")

    async def remove(self, uid, key):
        async with self.db.transaction() as tx:
            listing = await tx.one(
                "SELECT * FROM market_listings WHERE id=:id AND status='active' AND seller=:u",
                id=key,
                u=uid,
            )
            if not listing:
                raise ListingUnavailable()
            await tx.execute("UPDATE market_listings SET status='cancelled' WHERE id=:id", id=key)
            await tx.execute(
                "UPDATE owned_cards SET locked_reason=NULL WHERE id=:c", c=listing["card_id"]
            )

    async def trend(self, catalog, days=30):
        if days not in (7, 30):
            raise DomainError("Choose 7 or 30 days.")
        async with self.db.read() as tx:
            rows = await tx.all(
                "SELECT price,created_at FROM price_history WHERE catalog_card_id=:c AND created_at>=:t ORDER BY created_at DESC",
                c=catalog,
                t=self.now() - days * 86400,
            )
        prices = [x["price"] for x in rows]
        return {
            "days": days,
            "volume": len(prices),
            "median": median(prices) if prices else None,
            "min": min(prices) if prices else None,
            "max": max(prices) if prices else None,
            "last_sales": rows[:10],
        }

    async def sell_preview(self, uid):
        async with self.db.read() as tx:
            return await tx.all(
                "SELECT o.public_code,c.name,5+c.rarity*5 AS price FROM owned_cards o JOIN card_catalog c ON c.id=o.catalog_card_id WHERE o.owner_id=:u AND o.locked_reason IS NULL AND o.grade IS NULL AND o.favorite=0 AND c.rarity<4 ORDER BY o.id LIMIT 25",
                u=uid,
            )

    @audited
    async def sell(self, uid, codes, key):
        if not 1 <= len(codes) <= 25 or len(set(codes)) != len(codes):
            raise DomainError("Choose 1–25 unique cards.")
        async with self.db.transaction() as tx:
            old = await self.receipt(tx, uid, key, "sell")
            if old:
                return old["coins"]
            total = 0
            for code in codes:
                card = await self.available(tx, uid, code)
                catalog = await tx.one(
                    "SELECT rarity FROM card_catalog WHERE id=:c", c=card["catalog_card_id"]
                )
                if card["grade"] or card["favorite"] or catalog["rarity"] >= 4:
                    raise DomainError("This bulk sale includes a protected card.")
                await tx.execute(
                    "UPDATE owned_cards SET locked_reason='sold_system' WHERE id=:id", id=card["id"]
                )
                await tx.execute("DELETE FROM deck_cards WHERE card_id=:id", id=card["id"])
                total += 5 + catalog["rarity"] * 5
            await self.money(tx, uid, total, "SYSTEM_SALE", key)
            await self.save_receipt(tx, uid, key, "sell", {"coins": total})
            return total
