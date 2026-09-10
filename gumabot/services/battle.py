import json

from .core import Service
from .engines import GYMS, duel_state, duel_step
from .errors import DomainError, InvalidState


class Battle(Service):
    async def deck(self, uid, codes=None):
        async with self.db.transaction() as tx:
            await self.user(tx, uid)
            if codes is not None:
                if len(codes) != 5 or len(set(codes)) != 5:
                    raise DomainError("A deck needs exactly five different card instances.")
                cards = [await self.available(tx, uid, c) for c in codes]
                await tx.execute(
                    "INSERT INTO decks(user_id) VALUES (:u) ON CONFLICT DO NOTHING", u=uid
                )
                await tx.execute("DELETE FROM deck_cards WHERE user_id=:u", u=uid)
                for slot, card in enumerate(cards):
                    await tx.execute(
                        "INSERT INTO deck_cards VALUES (:u,:s,:c)", u=uid, s=slot, c=card["id"]
                    )
            return await tx.all(
                "SELECT o.public_code,c.name,c.rarity FROM deck_cards d JOIN owned_cards o ON o.id=d.card_id JOIN card_catalog c ON c.id=o.catalog_card_id WHERE d.user_id=:u AND o.owner_id=:u AND o.locked_reason IS NULL ORDER BY d.slot",
                u=uid,
            )

    async def power(self, tx, uid):
        rows = await tx.all(
            "SELECT c.rarity FROM deck_cards d JOIN owned_cards o ON o.id=d.card_id JOIN card_catalog c ON c.id=o.catalog_card_id WHERE d.user_id=:u AND o.owner_id=:u AND o.locked_reason IS NULL",
            u=uid,
        )
        if len(rows) != 5:
            raise DomainError("Both players need five available cards in /deck.")
        return sum(c["rarity"] for c in rows) // 5

    async def invite_duel(self, uid, opponent):
        if uid == opponent:
            raise DomainError("Choose another player.")
        async with self.db.transaction() as tx:
            powers = [await self.power(tx, u) for u in (uid, opponent)]
            key = self.identifier()
            await tx.execute(
                "INSERT INTO duels VALUES (:id,:u,:o,'invited',:s,:due,NULL)",
                id=key,
                u=uid,
                o=opponent,
                s=json.dumps(duel_state(powers)),
                due=self.now() + 1800,
            )
            return key

    async def accept_duel(self, uid, key):
        async with self.db.transaction() as tx:
            row = await tx.one(
                "SELECT * FROM duels WHERE id=:id AND opponent=:u AND status='invited' AND due_at>:t",
                id=key,
                u=uid,
                t=self.now(),
            )
            if not row:
                raise InvalidState()
            for player in (row["challenger"], uid):
                await self.power(tx, player)
                await self.cooldown(tx, player, "duel", 300)
                await tx.execute(
                    "UPDATE owned_cards SET locked_reason=:r WHERE id IN (SELECT card_id FROM deck_cards WHERE user_id=:u)",
                    r="duel:" + key,
                    u=player,
                )
            await tx.execute("UPDATE duels SET status='active' WHERE id=:id", id=key)

    async def duel_action(self, uid, key, action, expected_turn):
        async with self.db.transaction() as tx:
            row = await tx.one(
                "SELECT * FROM duels WHERE id=:id AND status='active' AND due_at>:t",
                id=key,
                t=self.now(),
            )
            if not row or uid not in (row["challenger"], row["opponent"]):
                raise InvalidState()
            state = json.loads(row["state"])
            if state["turn"] != expected_turn:
                raise DomainError("This turn has already been played. Refresh /duel.")
            actor = 0 if uid == row["challenger"] else 1
            duel_step(state, actor, action, self.rng)
            await tx.execute(
                "INSERT INTO duel_turns VALUES (:id,:turn,:u,:a)",
                id=key,
                turn=expected_turn,
                u=uid,
                a=action,
            )
            winner = (
                None
                if state["winner"] is None
                else (row["challenger"], row["opponent"])[state["winner"]]
            )
            await tx.execute(
                "UPDATE duels SET state=:s,status=:status,winner=:winner WHERE id=:id",
                s=json.dumps(state),
                status="completed" if winner else "active",
                winner=winner,
                id=key,
            )
            if winner:
                loser = row["opponent"] if winner == row["challenger"] else row["challenger"]
                for player in (winner, loser):
                    await tx.execute(
                        "INSERT INTO duel_profiles(user_id) VALUES (:u) ON CONFLICT DO NOTHING",
                        u=player,
                    )
                await tx.execute(
                    "UPDATE duel_profiles SET wins=wins+1,rating=rating+15,streak=streak+1 WHERE user_id=:u",
                    u=winner,
                )
                await tx.execute(
                    "UPDATE duel_profiles SET losses=losses+1,rating=MAX(0,rating-15),streak=0 WHERE user_id=:u",
                    u=loser,
                )
                await self.money(tx, winner, 25, "DUEL", key)
                await self.event(tx, winner, "duel", 30)
                await tx.execute(
                    "UPDATE owned_cards SET locked_reason=NULL WHERE locked_reason=:r",
                    r="duel:" + key,
                )
            return state

    async def gym(self, uid, index):
        if not 1 <= index <= 8:
            raise DomainError("Choose gym 1–8.")
        async with self.db.transaction() as tx:
            if index > 1 and not await tx.one(
                "SELECT 1 FROM badges WHERE user_id=:u AND gym=:g", u=uid, g=index - 1
            ):
                raise DomainError("Win the previous gym first.")
            power = await self.power(tx, uid)
            await self.cooldown(tx, uid, "gym", 1800)
            state = duel_state([power, index - 1])
            while state["winner"] is None:
                actor = state["turn"] % 2
                fighter = state["fighters"][actor]
                action = (
                    "heal"
                    if fighter["hp"] < 35 and fighter["heals"]
                    else "rarity"
                    if fighter["special"]
                    else "attack"
                )
                duel_step(state, actor, action, self.rng)
            won = state["winner"] == 0
            if won:
                await tx.execute(
                    "INSERT INTO gym_progress VALUES (:u,:g,1) ON CONFLICT(user_id,gym) DO UPDATE SET wins=wins+1",
                    u=uid,
                    g=index,
                )
                result = await tx.execute(
                    "INSERT INTO badges VALUES (:u,:g,:b) ON CONFLICT DO NOTHING",
                    u=uid,
                    g=index,
                    b=GYMS[index - 1][2],
                )
                if result.rowcount:
                    await self.money(tx, uid, 100 * index, "GYM_BADGE", f"gym:{uid}:{index}")
                await self.event(tx, uid, "gym", 30)
            return {
                "leader": GYMS[index - 1][0],
                "theme": GYMS[index - 1][1],
                "won": won,
                "battle": state,
            }
