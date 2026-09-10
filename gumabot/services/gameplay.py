"""Compatibility facade for battle, session and journey services."""

from .battle import Battle
from .journey import Journey
from .sessions import Sessions


class Gameplay(Battle, Sessions, Journey):
    def __init__(self, db, clock, cards, rng=None):
        super().__init__(db, clock, rng)
        self.cards = cards

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
