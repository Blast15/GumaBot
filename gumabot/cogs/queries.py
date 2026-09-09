import discord
from discord import app_commands

from ..services.errors import DomainError
from ..views.ui import send, show_sets


async def query(app, name, uid, set_id=""):
    if name in ("balance", "level"):
        user = await app.economy.balance(uid)
        if name == "level":
            return {
                "level": user["level"],
                "xp": user["xp"],
                "next_level_xp": 100 * user["level"] ** 2 if user["level"] < 50 else None,
            }
        return {k: user[k] for k in ("coins", "aura", "energy")}
    if name == "quests":
        return await app.progression.quests(uid)
    if name == "upcoming":
        return (
            await app.provider.get_upcoming_sets()
            or "No reliable upcoming release dates are cached. Dates are never guessed."
        )
    if name == "packs":
        return await app.provider.list_sets()
    if name == "cooldowns":
        await app.economy.balance(uid)
    async with app.db.read() as tx:
        await app.cards.user(tx, uid)
        if name == "collection":
            stats = await tx.one(
                "SELECT COUNT(*) AS total_owned,COUNT(DISTINCT catalog_card_id) AS unique_cards,SUM(grade IS NOT NULL) AS graded FROM owned_cards WHERE owner_id=:u AND (locked_reason IS NULL OR locked_reason NOT IN ('fusion_consumed','sold_system'))",
                u=uid,
            )
            distribution = await tx.all(
                "SELECT c.rarity,COUNT(*) AS count FROM owned_cards o JOIN card_catalog c ON c.id=o.catalog_card_id WHERE o.owner_id=:u AND (o.locked_reason IS NULL OR o.locked_reason NOT IN ('fusion_consumed','sold_system')) GROUP BY c.rarity",
                u=uid,
            )
            from ..services.rules import Rarity

            completed = await tx.one(
                "SELECT COUNT(*) AS n FROM (SELECT s.id FROM card_sets s JOIN card_catalog c ON c.set_id=s.id JOIN owned_cards o ON o.catalog_card_id=c.id WHERE o.owner_id=:u AND (o.locked_reason IS NULL OR o.locked_reason NOT IN ('fusion_consumed','sold_system')) GROUP BY s.id HAVING s.total>0 AND COUNT(DISTINCT c.id)>=s.total)",
                u=uid,
            )
            return {
                **stats,
                "sets_completed": completed["n"],
                "rarities": {Rarity(r["rarity"]).name: r["count"] for r in distribution},
            }
        if name == "setcompletion":
            return await tx.all(
                "SELECT s.id,s.name,s.total,COUNT(DISTINCT o.catalog_card_id) AS collected,CASE WHEN s.total>0 THEN MIN(100,100.0*COUNT(DISTINCT o.catalog_card_id)/s.total) ELSE 0 END AS percent FROM card_sets s LEFT JOIN card_catalog c ON c.set_id=s.id LEFT JOIN owned_cards o ON o.catalog_card_id=c.id AND o.owner_id=:u AND (o.locked_reason IS NULL OR o.locked_reason NOT IN ('fusion_consumed','sold_system')) GROUP BY s.id ORDER BY s.id LIMIT 25",
                u=uid,
            )
        if name == "missing":
            return await tx.all(
                "SELECT c.id,c.name FROM card_catalog c WHERE c.set_id=:s AND NOT EXISTS(SELECT 1 FROM owned_cards o WHERE o.owner_id=:u AND o.catalog_card_id=c.id AND (o.locked_reason IS NULL OR o.locked_reason NOT IN ('fusion_consumed','sold_system'))) ORDER BY c.id LIMIT 50",
                s=set_id or app.settings.featured_set,
                u=uid,
            )
        if name == "items":
            return await tx.all(
                "SELECT s.id,s.name,i.quantity FROM user_items i JOIN shop_items s ON s.id=i.item_id WHERE user_id=:u AND quantity>0",
                u=uid,
            )
        if name == "itemshop":
            return await tx.all("SELECT * FROM shop_items ORDER BY price")
        if name == "bag":
            return await tx.all(
                "SELECT item,quantity FROM journey_inventory WHERE user_id=:u AND quantity>0", u=uid
            )
        if name == "quizstats":
            return await tx.one(
                "SELECT *,CASE WHEN attempts>0 THEN 100.0*correct/attempts ELSE 0 END AS accuracy FROM quiz_stats WHERE user_id=:u",
                u=uid,
            ) or {"attempts": 0}
        if name == "duelprofile":
            return await tx.one(
                "SELECT *,CASE WHEN wins+losses>0 THEN 100.0*wins/(wins+losses) ELSE 0 END AS win_rate FROM duel_profiles WHERE user_id=:u",
                u=uid,
            ) or {"wins": 0, "losses": 0, "rating": 1000}
        if name == "achievements":
            return await tx.all(
                "SELECT a.id,a.target,u.progress,u.awarded FROM achievements a LEFT JOIN user_achievements u ON u.achievement_id=a.id AND u.user_id=:u",
                u=uid,
            )
        if name == "season":
            return {
                "season": app.clock.now().strftime("%Y-%m"),
                "leaders": await tx.all(
                    "SELECT user_id,points,RANK() OVER (ORDER BY points DESC) AS rank FROM season_stats WHERE season_id=:s ORDER BY points DESC,user_id LIMIT 10",
                    s=app.clock.now().strftime("%Y-%m"),
                ),
                "hall_of_fame": await tx.all(
                    "SELECT * FROM hall_of_fame ORDER BY season_id DESC,rank LIMIT 10"
                ),
            }
        if name == "serverleaderboard":
            return await tx.all(
                "SELECT g.guild_id,COUNT(*) AS registered_members,ROUND(AVG(u.xp),1) AS average_xp,RANK() OVER (ORDER BY AVG(u.xp) DESC) AS rank FROM guild_members g JOIN users u ON u.discord_user_id=g.user_id GROUP BY g.guild_id ORDER BY average_xp DESC,g.guild_id LIMIT 10"
            )
        if name == "cooldowns":
            rows = await tx.all(
                "SELECT kind,due_at FROM cooldowns WHERE user_id=:u ORDER BY kind", u=uid
            )
            user = await app.cards.user(tx, uid)
            result = {r["kind"]: f"<t:{r['due_at']}:R>" for r in rows}
            result["energy"] = (
                "Full" if user["energy"] >= 3 else f"<t:{user['energy_updated_at'] + 7200}:R>"
            )
            return result
    raise DomainError("Unknown query.")


def install_queries(bot):
    descriptions = {
        "balance": "View coins, Aura and energy",
        "level": "View XP and progress to level 50",
        "collection": "View collection totals and rarity distribution",
        "setcompletion": "View locally known set completion",
        "missing": "List missing cards from a locally cached set",
        "items": "View your shop items",
        "itemshop": "View item prices",
        "bag": "View Journey consumables; use /journey potion to heal",
        "quizstats": "View quiz accuracy and streaks",
        "duelprofile": "View duel wins, losses and rating",
        "achievements": "View achievement progress",
        "quests": "View three daily quests and automatic rewards",
        "season": "View current monthly season and Hall of Fame",
        "serverleaderboard": "Compare average XP of registered server players",
        "cooldowns": "View cooldown timestamps and energy ETA",
        "upcoming": "View verified cached upcoming release dates",
        "packs": "List provider card sets",
    }
    for name, description in descriptions.items():

        def make_callback(command_name):
            async def callback(i: discord.Interaction, set_id: str = ""):
                await i.response.defer(ephemeral=True)
                if command_name == "packs":
                    await show_sets(i, bot.app)
                    return
                await send(
                    i, command_name.title(), await query(bot.app, command_name, i.user.id, set_id)
                )

            return callback

        bot.tree.add_command(
            app_commands.Command(name=name, description=description, callback=make_callback(name))
        )
