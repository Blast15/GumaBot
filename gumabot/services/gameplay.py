import json

from .core import Service
from .engines import GYMS, QUESTIONS, blackjack_total, duel_state, duel_step
from .errors import DomainError, InvalidState
from .rules import normalize


class Gameplay(Service):
    def __init__(self, db, clock, cards, rng=None):
        super().__init__(db, clock, rng)
        self.cards = cards

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

    async def new_session(self, uid, kind, set_id="base1", wager=0):
        pool = await self.cards.ensure_set(set_id) if kind in ("pickcard", "namepokemon") else None
        if kind == "namepokemon":
            pool = [
                card for card in pool if json.loads(card["metadata"]).get("category") == "Pokemon"
            ]
            if not pool:
                raise DomainError("No Pokémon images are available in this set.")
        async with self.db.transaction() as tx:
            if kind == "blackjack":
                self.positive(wager, 500)
            await self.cooldown(tx, uid, kind, 1800 if kind == "pickcard" else 300)
            key = self.identifier()
            if kind == "quiz":
                state = {
                    "order": self.rng.sample(range(len(QUESTIONS)), 10),
                    "position": 0,
                    "correct": 0,
                }
            elif kind == "pickcard":
                state = {"choices": [c["id"] for c in self.rng.choices(pool, k=3)]}
            elif kind == "namepokemon":
                card = self.rng.choice(pool)
                state = {"card": card["id"], "answer": normalize(card["name"])}
            elif kind == "blackjack":
                await self.money(tx, uid, -wager, "BLACKJACK_WAGER", key)
                deck = [n for n in range(1, 14) for _ in range(4)]
                self.rng.shuffle(deck)
                state = {
                    "player": [deck.pop(), deck.pop()],
                    "dealer": [deck.pop(), deck.pop()],
                    "deck": deck,
                    "wager": wager,
                }
            else:
                raise DomainError("Unknown game.")
            await tx.execute(
                "INSERT INTO quiz_attempts VALUES (:id,:u,:k,:s,:due,0)",
                id=key,
                u=uid,
                k=kind,
                s=json.dumps(state),
                due=self.now() + 600,
            )
            return key

    async def session_action(self, uid, key, answer, position=0):
        async with self.db.transaction() as tx:
            row = await tx.one(
                "SELECT * FROM quiz_attempts WHERE id=:id AND user_id=:u AND completed=0 AND due_at>:t",
                id=key,
                u=uid,
                t=self.now(),
            )
            if not row:
                raise InvalidState()
            state, kind = json.loads(row["state"]), row["kind"]
            complete, result = True, {}
            if kind == "quiz":
                if position != state["position"]:
                    raise InvalidState()
                correct = str(QUESTIONS[state["order"][position]][2]) == str(answer)
                state["position"] += 1
                state["correct"] += correct
                complete = state["position"] == 10
                await self.quiz_reward(tx, uid, correct, key)
                result = {"correct": correct, "score": state["correct"]}
            elif kind == "namepokemon":
                correct = normalize(str(answer)) == state["answer"]
                await self.quiz_reward(tx, uid, correct, key)
                result = {"correct": correct, "answer": state["answer"]}
            elif kind == "pickcard":
                if str(answer) not in ("0", "1", "2"):
                    raise DomainError("Choose card 1, 2 or 3.")
                result = {
                    "card": await self.cards.mint(
                        tx, uid, state["choices"][int(answer)], "pickcard"
                    )
                }
            else:
                if position != len(state["player"]):
                    raise InvalidState()
                if answer not in ("hit", "stand"):
                    raise DomainError("Choose hit or stand.")
                if answer == "hit":
                    state["player"].append(state["deck"].pop())
                total = blackjack_total(state["player"])
                complete = answer == "stand" or total >= 21
                if complete:
                    while blackjack_total(state["dealer"]) < 17:
                        state["dealer"].append(state["deck"].pop())
                    dealer = blackjack_total(state["dealer"])
                    payout = (
                        0
                        if total > 21
                        else 2 * state["wager"]
                        if dealer > 21 or total > dealer
                        else state["wager"]
                        if total == dealer
                        else 0
                    )
                    await self.money(tx, uid, payout, "BLACKJACK_SETTLE", key)
                    result = {"player": total, "dealer": dealer, "payout": payout}
            await tx.execute(
                "UPDATE quiz_attempts SET state=:s,completed=:c WHERE id=:id",
                s=json.dumps(state),
                c=int(complete),
                id=key,
            )
            return {"complete": complete, **result}

    async def quiz_reward(self, tx, uid, correct, key):
        await tx.execute(
            "INSERT INTO quiz_stats(user_id) VALUES (:u) ON CONFLICT DO NOTHING", u=uid
        )
        await tx.execute(
            "UPDATE quiz_stats SET attempts=attempts+1,correct=correct+:c,streak=CASE WHEN :c=1 THEN streak+1 ELSE 0 END,rewards=rewards+:r WHERE user_id=:u",
            c=int(correct),
            r=5 if correct else 0,
            u=uid,
        )
        await tx.execute(
            "UPDATE quiz_stats SET best_streak=MAX(best_streak,streak) WHERE user_id=:u", u=uid
        )
        if correct:
            await self.money(tx, uid, 5, "QUIZ", key)
            await self.money(tx, uid, 1, "QUIZ", key, "aura")
            await self.event(tx, uid, "quiz", 5)

    async def journey(self, uid, action="explore"):
        if action not in ("explore", "rest", "potion"):
            raise DomainError("Choose explore, rest or potion.")
        async with self.db.transaction() as tx:
            await self.user(tx, uid)
            await tx.execute(
                "INSERT INTO journey_progress(user_id) VALUES (:u) ON CONFLICT DO NOTHING", u=uid
            )
            row = await tx.one("SELECT * FROM journey_progress WHERE user_id=:u", u=uid)
            if action == "potion":
                result = await tx.execute(
                    "UPDATE journey_inventory SET quantity=quantity-1 WHERE user_id=:u AND item='potion' AND quantity>0",
                    u=uid,
                )
                if result.rowcount != 1:
                    raise DomainError("No potions in your bag.")
                row["hp"] = min(100, row["hp"] + 40)
                encounter = "Restored 40 HP."
            else:
                await self.cooldown(tx, uid, "journey", 300)
                if action == "rest":
                    row["hp"] = min(100, row["hp"] + 25)
                    encounter = "Camp: restored 25 HP."
                else:
                    if row["hp"] < 20:
                        raise DomainError("Low HP. Rest or use a potion.")
                    event = self.rng.choice(["battle", "treasure", "spring", "supplies"])
                    encounter = event
                    if event == "battle":
                        row["hp"] -= self.rng.randint(5, 19)
                    elif event == "spring":
                        row["hp"] = min(100, row["hp"] + 15)
                    elif event == "supplies":
                        await tx.execute(
                            "INSERT INTO journey_inventory VALUES (:u,'potion',1) ON CONFLICT(user_id,item) DO UPDATE SET quantity=quantity+1",
                            u=uid,
                        )
                    await self.money(
                        tx, uid, 5 + min(row["stage"], 50), "JOURNEY", f"journey:{uid}:{self.now()}"
                    )
                    row["encounters"] += 1
                    row["stage"] = 1 + row["encounters"] // 3
                    await self.event(tx, uid, "journey", 10)
            await tx.execute(
                "UPDATE journey_progress SET hp=:hp,stage=:stage,encounters=:encounters WHERE user_id=:user_id",
                **row,
            )
            return {**row, "event": encounter}

    async def expire(self):
        async with self.db.transaction() as tx:
            for row in await tx.all(
                "SELECT id FROM duels WHERE status IN ('active','invited') AND due_at<=:t LIMIT 100",
                t=self.now(),
            ):
                await tx.execute("UPDATE duels SET status='expired' WHERE id=:id", id=row["id"])
                await tx.execute(
                    "UPDATE owned_cards SET locked_reason=NULL WHERE locked_reason=:r",
                    r="duel:" + row["id"],
                )
            # Expired blackjack wagers are forfeited, never refunded to avoid losing-hand resets.
            await tx.execute(
                "UPDATE quiz_attempts SET completed=1 WHERE completed=0 AND due_at<=:t",
                t=self.now(),
            )
