import json
from typing import Any

from .core import Service
from .engines import blackjack_total
from .errors import DomainError, InvalidState
from .quiz import build_questions, question_at
from .rules import normalize


class Sessions(Service):
    cards: Any

    async def new_session(self, uid, kind, set_id="base1", wager=0):
        pool = await self.cards.ensure_set(set_id) if kind in ("pickcard", "namepokemon") else []
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
                    "questions": build_questions(
                        await tx.all(
                            "SELECT id,name,metadata FROM card_catalog ORDER BY id LIMIT 5000"
                        ),
                        self.rng,
                    ),
                    "position": 0,
                    "correct": 0,
                }
            elif kind == "pickcard":
                state = {"choices": [c["id"] for c in self.rng.sample(pool, k=min(3, len(pool)))]}
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
                correct = str(question_at(state, position)[2]) == str(answer)
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
                count = len(state["choices"])
                if str(answer) not in {str(i) for i in range(count)}:
                    raise DomainError(f"Choose one of the {count} available cards.")
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
