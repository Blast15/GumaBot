import re
import secrets

from ..utils.audit import audited
from .core import Service
from .errors import DomainError, InsufficientEnergy
from .rules import Rarity, condition, normalize, roll_pack


class Cards(Service):
    def __init__(self, db, clock, provider, rng=None):
        super().__init__(db, clock, rng)
        self.provider = provider

    async def ensure_set(self, set_id):
        self.provider.identifier(set_id)
        async with self.db.read() as tx:
            rows = await tx.all("SELECT * FROM card_catalog WHERE set_id=:s", s=set_id)
        if not rows or not any(c["rarity"] >= Rarity.Holo for c in rows):
            await self.provider.get_set_cards(set_id)
            async with self.db.read() as tx:
                rows = await tx.all("SELECT * FROM card_catalog WHERE set_id=:s", s=set_id)
        if not rows or not any(c["rarity"] >= Rarity.Holo for c in rows):
            raise DomainError("This set has no available Holo-or-higher pool. Choose another set.")
        return rows

    async def mint(self, tx, uid, catalog, source, score=None):
        score = self.rng.randint(0, 100) if score is None else score
        for _ in range(10):
            code = "GUMA-" + "".join(
                secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8)
            )
            result = await tx.execute(
                "INSERT INTO owned_cards(public_code,owner_id,catalog_card_id,condition_score,condition_name,created_at,acquisition_source) VALUES (:code,:u,:c,:score,:condition,:t,:source) ON CONFLICT(public_code) DO NOTHING",
                code=code,
                u=uid,
                c=catalog,
                score=score,
                condition=condition(score),
                t=self.now(),
                source=source,
            )
            if result.rowcount:
                await self.acquired(tx, uid, catalog)
                return code
        raise DomainError("Could not allocate a card code. Please retry.")

    @audited
    async def start(self, uid, set_id):
        async with self.db.read() as tx:
            if await tx.one("SELECT 1 FROM users WHERE discord_user_id=:u", u=uid):
                return {"message": "You are already registered. Use /play."}
        pool = await self.ensure_set(set_id)
        async with self.db.transaction() as tx:
            result = await tx.execute(
                "INSERT INTO users(discord_user_id,created_at,energy_updated_at) VALUES (:u,:t,:t) ON CONFLICT DO NOTHING",
                u=uid,
                t=self.now(),
            )
            if not result.rowcount:
                return {"message": "You are already registered. Use /play."}
            await self.money(tx, uid, 150, "START_REWARD", f"start:{uid}")
            return await self._pack(tx, uid, set_id, pool, f"starter:{uid}", True)

    async def _pack(self, tx, uid, set_id, pool, key, starter=False, boosted=False):
        groups = {
            r: [c for c in pool if c["rarity"] == r] for r in sorted({c["rarity"] for c in pool})
        }
        ranks, god = roll_pack(self.rng, list(groups), guaranteed=starter, boosted=boosted)
        await tx.execute(
            "INSERT INTO pack_openings VALUES (:id,:u,:s,:god,:t)",
            id=key,
            u=uid,
            s=set_id,
            god=int(god),
            t=self.now(),
        )
        pulls = []
        for slot, rank in enumerate(ranks):
            card = self.rng.choice(groups[rank])
            code = await self.mint(tx, uid, card["id"], "starter" if starter else "pack")
            await tx.execute(
                "INSERT INTO pack_pulls VALUES (:id,:slot,:code,:c)",
                id=key,
                slot=slot,
                code=code,
                c=card["id"],
            )
            pulls.append({"code": code, "name": card["name"], "rarity": Rarity(rank).name})
            if rank >= Rarity.Holo:
                await self.event(tx, uid, "holo", 0)
        await self.event(tx, uid, "pack", 20)
        await self.milestones(tx, uid, set_id)
        result = {"pack": key, "god": god, "cards": pulls}
        await self.save_receipt(tx, uid, key, "pack", result)
        return result

    @audited
    async def open_pack(self, uid, set_id, key):
        pool = await self.ensure_set(set_id)
        async with self.db.transaction() as tx:
            old = await self.receipt(tx, uid, key, "pack")
            if old:
                return old
            value = await self.refresh_energy(tx, uid)
            meter = await tx.one(
                "SELECT progress FROM chase_meters WHERE user_id=:u AND set_id=:s", u=uid, s=set_id
            )
            boosted = bool(meter and meter["progress"] >= 10)
            if not boosted:
                if value < 1:
                    raise InsufficientEnergy()
                await self.add_energy(tx, uid, -1, "PACK")
            await tx.execute(
                "INSERT INTO chase_meters VALUES (:u,:s,1) ON CONFLICT(user_id,set_id) DO UPDATE SET progress=:p",
                u=uid,
                s=set_id,
                p=0 if boosted else (meter["progress"] if meter else 0) + 1,
            )
            return await self._pack(tx, uid, set_id, pool, key, boosted=boosted)

    async def inventory(
        self,
        uid,
        page=0,
        name="",
        set_id="",
        rarity=None,
        condition_name="",
        graded=None,
        duplicate=False,
        sort="newest",
    ):
        orders = {
            "newest": "o.created_at DESC,o.id DESC",
            "oldest": "o.created_at,o.id",
            "rarity": "c.rarity DESC,o.id",
            "condition": "o.condition_score DESC,o.id",
            "grade": "o.grade DESC,c.rarity DESC,o.condition_score DESC,o.id",
            "set": "c.set_id,o.id",
        }
        if sort not in orders or not 0 <= page <= 100000:
            raise DomainError("Invalid sort or page.")
        sql = "SELECT o.*,c.name,c.rarity,c.set_id,c.metadata FROM owned_cards o JOIN card_catalog c ON c.id=o.catalog_card_id WHERE o.owner_id=:u AND (o.locked_reason IS NULL OR o.locked_reason NOT IN ('fusion_consumed','sold_system'))"
        params = {"u": uid, "offset": page * 10}
        for value, clause, key in [
            (normalize(name), "instr(c.search_name,:name)>0", "name"),
            (set_id, "c.set_id=:set", "set"),
            (condition_name, "o.condition_name=:condition", "condition"),
        ]:
            if value:
                sql += " AND " + clause
                params[key] = value
        if rarity is not None:
            sql += " AND c.rarity=:rarity"
            params["rarity"] = rarity
        if graded is not None:
            sql += " AND o.grade IS " + ("NOT NULL" if graded else "NULL")
        if duplicate:
            sql += " AND (SELECT COUNT(*) FROM owned_cards d WHERE d.owner_id=o.owner_id AND d.catalog_card_id=o.catalog_card_id)>1"
        async with self.db.read() as tx:
            return await tx.all(
                sql + " ORDER BY " + orders[sort] + " LIMIT 10 OFFSET :offset", **params
            )

    async def find(self, uid, name):
        rows = await self.inventory(uid, name=name)
        if rows:
            return rows
        import difflib

        async with self.db.read() as tx:
            names = await tx.all(
                "SELECT DISTINCT c.search_name FROM owned_cards o JOIN card_catalog c ON c.id=o.catalog_card_id WHERE o.owner_id=:u AND (o.locked_reason IS NULL OR o.locked_reason NOT IN ('fusion_consumed','sold_system')) LIMIT 5000",
                u=uid,
            )
        matches = difflib.get_close_matches(
            normalize(name), [r["search_name"] for r in names], n=1, cutoff=0.55
        )
        return await self.inventory(uid, name=matches[0]) if matches else []

    async def search(self, uid, code):
        async with self.db.read() as tx:
            row = await tx.one(
                "SELECT o.*,c.name,c.rarity,c.set_id,c.metadata FROM owned_cards o JOIN card_catalog c ON c.id=o.catalog_card_id WHERE o.public_code=:c AND o.owner_id=:u",
                c=code.upper(),
                u=uid,
            )
            if not row:
                raise DomainError("Card not found in your inventory.")
            return row

    @audited
    async def fuse(self, uid, codes):
        if len(set(codes)) != 3:
            raise DomainError("Select three different duplicate instances.")
        async with self.db.transaction() as tx:
            cards = [await self.available(tx, uid, code) for code in codes]
            if len({c["catalog_card_id"] for c in cards}) != 1 or any(c["grade"] for c in cards):
                raise DomainError("Fusion needs three raw copies of the same card.")
            for card in cards:
                # Keep consumed instances for permanent provenance and FK references.
                await tx.execute(
                    "UPDATE owned_cards SET locked_reason='fusion_consumed' WHERE id=:id",
                    id=card["id"],
                )
                await tx.execute("DELETE FROM deck_cards WHERE card_id=:id", id=card["id"])
            return await self.mint(
                tx,
                uid,
                cards[0]["catalog_card_id"],
                "fusion",
                min(100, max(c["condition_score"] for c in cards) + 10),
            )

    async def swap_codes(self, uid, a, b):
        if a == b:
            raise DomainError("Choose two different codes.")
        async with self.db.transaction() as tx:
            first, second = await self.available(tx, uid, a), await self.available(tx, uid, b)
            temporary = "SWAP-" + self.identifier()
            for card, code in [
                (first, temporary),
                (second, first["public_code"]),
                (first, second["public_code"]),
            ]:
                await tx.execute(
                    "UPDATE owned_cards SET public_code=:c WHERE id=:id", c=code, id=card["id"]
                )

    async def tint(self, uid, code, color):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise DomainError("Use a color such as #33AACC.")
        async with self.db.transaction() as tx:
            card = await self.available(tx, uid, code)
            await self.item(tx, uid, "tint", -1)
            await tx.execute("UPDATE owned_cards SET tint=:t WHERE id=:id", t=color, id=card["id"])

    async def wishlist(self, uid, action, card_id=""):
        if action == "add":
            await self.provider.get_card(card_id)
        async with self.db.transaction() as tx:
            await self.user(tx, uid)
            if action == "add":
                await tx.execute(
                    "INSERT INTO wishlists VALUES (:u,:c) ON CONFLICT DO NOTHING", u=uid, c=card_id
                )
            elif action == "remove":
                await tx.execute(
                    "DELETE FROM wishlists WHERE user_id=:u AND card_id=:c", u=uid, c=card_id
                )
            return await tx.all(
                "SELECT c.id,c.name FROM wishlists w JOIN card_catalog c ON w.card_id=c.id WHERE w.user_id=:u LIMIT 100",
                u=uid,
            )
