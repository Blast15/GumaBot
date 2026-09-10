from .core import Service
from .errors import DomainError


class Progression(Service):
    async def rollover(self):
        async with self.db.transaction() as tx:
            seasons = await tx.all(
                "SELECT * FROM seasons WHERE settled=0 AND ends_at<=:t LIMIT 12", t=self.now()
            )
            for season in seasons:
                result = await tx.execute(
                    "UPDATE seasons SET settled=1 WHERE id=:id AND settled=0", id=season["id"]
                )
                if not result.rowcount:
                    continue
                leaders = await tx.all(
                    "SELECT * FROM season_stats WHERE season_id=:s ORDER BY points DESC,user_id LIMIT 10",
                    s=season["id"],
                )
                for rank, player in enumerate(leaders, 1):
                    await tx.execute(
                        "INSERT INTO hall_of_fame VALUES (:s,:r,:u,:p)",
                        s=season["id"],
                        r=rank,
                        u=player["user_id"],
                        p=player["points"],
                    )
                    await self.money(
                        tx, player["user_id"], (11 - rank) * 100, "SEASON", season["id"]
                    )
            return len(seasons)

    async def leaderboard(self, metric="coins", page=0):
        metrics = {
            "coins": "u.coins",
            "aura": "u.aura",
            "xp": "u.xp",
            "collection": "(SELECT COUNT(DISTINCT catalog_card_id) FROM owned_cards WHERE owner_id=u.discord_user_id AND (locked_reason IS NULL OR locked_reason NOT IN ('fusion_consumed','sold_system')))",
            "grades": "(SELECT COUNT(*) FROM owned_cards WHERE owner_id=u.discord_user_id AND grade IS NOT NULL)",
            "duels": "COALESCE((SELECT wins FROM duel_profiles WHERE user_id=u.discord_user_id),0)",
            "achievements": "(SELECT COUNT(*) FROM user_achievements WHERE user_id=u.discord_user_id AND awarded=1)",
        }
        if metric not in metrics or not 0 <= page <= 100000:
            raise DomainError("Invalid leaderboard selection.")
        async with self.db.read() as tx:
            return await tx.all(
                f"SELECT discord_user_id,{metrics[metric]} AS score,RANK() OVER (ORDER BY {metrics[metric]} DESC) AS rank FROM users u ORDER BY score DESC,discord_user_id LIMIT 10 OFFSET :offset",
                offset=page * 10,
            )

    async def reminder(self, uid, kind, enabled):
        if kind not in ("daily", "energy", "grading", "auction", "pickcard"):
            raise DomainError("Unknown reminder type.")
        async with self.db.transaction() as tx:
            await self.user(tx, uid)
            await tx.execute(
                "INSERT INTO reminder_preferences(user_id,kind,enabled,last_sent) VALUES (:u,:k,:e,0) ON CONFLICT(user_id,kind) DO UPDATE SET enabled=:e",
                u=uid,
                k=kind,
                e=int(enabled),
            )

    async def report(self, uid, body):
        if not 10 <= len(body) <= 2000:
            raise DomainError("Report must contain 10–2000 characters.")
        async with self.db.transaction() as tx:
            await self.cooldown(tx, uid, "report", 300)
            await tx.execute(
                "INSERT INTO reports(user_id,body,created_at) VALUES (:u,:b,:t)",
                u=uid,
                b=body,
                t=self.now(),
            )

    async def quests(self, uid):
        async with self.db.transaction() as tx:
            await self.event(tx, uid, "view", 0)
            return await tx.all(
                "SELECT q.id,q.target,q.reward,u.progress,u.claimed FROM user_quests u JOIN quests q ON q.id=u.quest_id WHERE u.user_id=:u AND u.day=:day",
                u=uid,
                day=self.clock.now().date().isoformat(),
            )
