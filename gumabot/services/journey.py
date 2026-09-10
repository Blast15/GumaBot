from .core import Service
from .errors import DomainError


class Journey(Service):
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
