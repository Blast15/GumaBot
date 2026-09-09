from ..utils.audit import audited
from .core import Service
from .errors import DomainError, InvalidState, TradeExpired


class Trades(Service):
    async def invite(self, uid, recipient):
        if uid == recipient:
            raise DomainError("Choose another player.")
        async with self.db.transaction() as tx:
            await self.user(tx, uid)
            await self.user(tx, recipient)
            key = self.identifier()
            await tx.execute(
                "INSERT INTO trades(id,proposer,recipient,status,due_at) VALUES (:id,:u,:r,'INVITED',:due)",
                id=key,
                u=uid,
                r=recipient,
                due=self.now() + 1800,
            )
            return key

    async def load(self, tx, uid, key):
        row = await tx.one("SELECT * FROM trades WHERE id=:id", id=key)
        if not row or uid not in (row["proposer"], row["recipient"]):
            raise InvalidState()
        if row["due_at"] <= self.now():
            raise TradeExpired()
        if row["status"] in ("COMPLETED", "CANCELLED", "EXPIRED"):
            raise InvalidState()
        return row

    async def accept(self, uid, key):
        async with self.db.transaction() as tx:
            trade = await self.load(tx, uid, key)
            if uid != trade["recipient"] or trade["status"] != "INVITED":
                raise InvalidState()
            await tx.execute("UPDATE trades SET status='ACTIVE' WHERE id=:id", id=key)

    async def add(self, uid, key, kind, reference="coins", amount=1):
        self.positive(amount)
        if kind not in ("card", "coins", "item"):
            raise DomainError("Choose card, coins or item.")
        async with self.db.transaction() as tx:
            trade = await self.load(tx, uid, key)
            if trade["status"] == "INVITED":
                raise InvalidState()
            count = await tx.one("SELECT COUNT(*) AS n FROM trade_items WHERE trade_id=:id", id=key)
            if count["n"] >= 20:
                raise DomainError("Maximum 20 trade entries.")
            if kind == "card":
                card = await self.available(tx, uid, reference)
                reference, amount = str(card["id"]), 1
                await tx.execute(
                    "UPDATE owned_cards SET locked_reason=:reason WHERE id=:c",
                    reason="trade:" + key,
                    c=card["id"],
                )
            elif kind == "coins":
                reference = "coins"
                await self.money(tx, uid, -amount, "TRADE_HOLD", key)
            else:
                await self.item(tx, uid, reference, -amount)
            await tx.execute(
                "INSERT INTO trade_items VALUES (:id,:u,:k,:r,:a) ON CONFLICT(trade_id,user_id,kind,reference) DO UPDATE SET amount=amount+:a",
                id=key,
                u=uid,
                k=kind,
                r=reference,
                a=amount,
            )
            await tx.execute(
                "UPDATE trades SET status='ACTIVE',proposer_confirmed=0,recipient_confirmed=0 WHERE id=:id",
                id=key,
            )

    @audited
    async def confirm(self, uid, key):
        async with self.db.transaction() as tx:
            trade = await self.load(tx, uid, key)
            if trade["status"] == "INVITED":
                raise InvalidState()
            column = "proposer_confirmed" if uid == trade["proposer"] else "recipient_confirmed"
            await tx.execute(f"UPDATE trades SET {column}=1,status='LOCKED' WHERE id=:id", id=key)
            trade = await self.load(tx, uid, key)
            if not trade["proposer_confirmed"] or not trade["recipient_confirmed"]:
                return "Waiting for the other player."
            items = await tx.all("SELECT * FROM trade_items WHERE trade_id=:id", id=key)
            if not items:
                raise DomainError("Add an offer first.")
            await tx.execute("UPDATE trades SET status='CONFIRMED' WHERE id=:id", id=key)
            for item in items:
                recipient = (
                    trade["recipient"]
                    if item["user_id"] == trade["proposer"]
                    else trade["proposer"]
                )
                if item["kind"] == "card":
                    result = await tx.execute(
                        "UPDATE owned_cards SET owner_id=:u,locked_reason=NULL WHERE id=:c AND owner_id=:old AND locked_reason=:reason",
                        u=recipient,
                        c=int(item["reference"]),
                        old=item["user_id"],
                        reason="trade:" + key,
                    )
                    if result.rowcount != 1:
                        raise InvalidState()
                    await tx.execute(
                        "DELETE FROM deck_cards WHERE card_id=:c", c=int(item["reference"])
                    )
                    await self.transferred(tx, recipient, int(item["reference"]))
                elif item["kind"] == "coins":
                    await self.money(tx, recipient, item["amount"], "TRADE", key)
                else:
                    await self.item(tx, recipient, item["reference"], item["amount"])
            await tx.execute("UPDATE trades SET status='COMPLETED' WHERE id=:id", id=key)
            await self.event(tx, trade["proposer"], "trade")
            await self.event(tx, trade["recipient"], "trade")
            return "Trade completed."

    async def release(self, tx, row, status):
        for item in await tx.all("SELECT * FROM trade_items WHERE trade_id=:id", id=row["id"]):
            if item["kind"] == "card":
                await tx.execute(
                    "UPDATE owned_cards SET locked_reason=NULL WHERE id=:c AND locked_reason=:r",
                    c=int(item["reference"]),
                    r="trade:" + row["id"],
                )
            elif item["kind"] == "coins":
                await self.money(tx, item["user_id"], item["amount"], "TRADE_RELEASE", row["id"])
            else:
                await self.item(tx, item["user_id"], item["reference"], item["amount"])
        await tx.execute("UPDATE trades SET status=:s WHERE id=:id", s=status, id=row["id"])

    async def cancel(self, uid, key):
        async with self.db.transaction() as tx:
            row = await self.load(tx, uid, key)
            await self.release(tx, row, "CANCELLED")

    async def expire(self):
        async with self.db.transaction() as tx:
            for row in await tx.all(
                "SELECT * FROM trades WHERE due_at<=:t AND status IN ('INVITED','ACTIVE','LOCKED','CONFIRMED') LIMIT 100",
                t=self.now(),
            ):
                await self.release(tx, row, "EXPIRED")
