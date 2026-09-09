from ..utils.audit import audited
from .core import Service
from .errors import DomainError
from .rules import LANES, subgrades


class Grading(Service):
    async def submit(self, uid, code, lane="economy", coupon=False):
        if lane not in LANES:
            raise DomainError("Lanes: express, fast, standard, economy.")
        fee, delay = LANES[lane]
        async with self.db.transaction() as tx:
            card = await self.available(tx, uid, code)
            if card["grade"]:
                raise DomainError("This card is already graded.")
            key = self.identifier()
            if coupon:
                await self.item(tx, uid, "coupon", -1)
                fee = max(0, fee - 50)
            await self.money(tx, uid, -fee, "GRADING", key)
            await tx.execute(
                "UPDATE owned_cards SET locked_reason='grading',grade_status='pending' WHERE id=:c",
                c=card["id"],
            )
            await tx.execute(
                "INSERT INTO grading_jobs VALUES (:id,:c,:u,:lane,:due,NULL)",
                id=key,
                c=card["id"],
                u=uid,
                lane=lane,
                due=self.now() + delay,
            )
            return {"job": key, "due_at": self.now() + delay, "fee": fee}

    @audited
    async def complete_due(self):
        async with self.db.transaction() as tx:
            jobs = await tx.all(
                "SELECT g.*,o.condition_score FROM grading_jobs g JOIN owned_cards o ON g.card_id=o.id WHERE completed_at IS NULL AND due_at<=:t LIMIT 100",
                t=self.now(),
            )
            for job in jobs:
                result = await tx.execute(
                    "UPDATE grading_jobs SET completed_at=:t WHERE id=:id AND completed_at IS NULL",
                    t=self.now(),
                    id=job["id"],
                )
                if not result.rowcount:
                    continue
                grades, final = subgrades(self.rng, job["condition_score"])
                await tx.execute(
                    "INSERT INTO grade_certificates VALUES (:id,:job,:c,:a,:b,:d,:e,:grade,:t)",
                    id="GUMA-CERT-" + self.identifier(),
                    job=job["id"],
                    c=job["card_id"],
                    a=grades[0],
                    b=grades[1],
                    d=grades[2],
                    e=grades[3],
                    grade=final,
                    t=self.now(),
                )
                await tx.execute(
                    "UPDATE owned_cards SET locked_reason=NULL,grade_status='graded',grade=:g WHERE id=:c",
                    g=final,
                    c=job["card_id"],
                )
                await self.event(tx, job["user_id"], "grade", 25)
            return len(jobs)

    async def check(self, uid, code):
        async with self.db.read() as tx:
            return await tx.one(
                "SELECT o.public_code,o.condition_name,o.grade_status,o.grade,g.due_at,c.id AS certificate,c.centering,c.corners,c.edges,c.surface,(SELECT COUNT(*) FROM grade_certificates gc JOIN owned_cards oc ON gc.card_id=oc.id WHERE oc.catalog_card_id=o.catalog_card_id AND gc.final_grade=o.grade) AS population FROM owned_cards o LEFT JOIN grading_jobs g ON g.card_id=o.id LEFT JOIN grade_certificates c ON c.card_id=o.id WHERE o.owner_id=:u AND o.public_code=:code",
                u=uid,
                code=code.upper(),
            )
