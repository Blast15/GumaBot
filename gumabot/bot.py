import logging
import time

import discord
from discord.ext import commands

from .cogs.commands import GameCommands
from .cogs.groups import AdminGroup, AuctionGroup, MarketGroup, WishlistGroup
from .cogs.queries import install_queries, query
from .jobs.manager import Jobs
from .services.errors import DomainError
from .views.ui import GuessModal, buttons, reveal_pack, send, show_duel, show_session, show_sets

log = logging.getLogger(__name__)


class GumaBot(commands.Bot):
    def __init__(self, app):
        intents = discord.Intents.default()
        intents.message_content = False
        intents.members = False
        intents.presences = False
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.app = app
        self.jobs = Jobs(self)
        self.activity_counts = {}
        self.tree.on_error = self.command_error

    async def register(self):
        await self.add_cog(GameCommands(self))
        for group in (
            MarketGroup(self.app),
            MarketGroup(self.app, "shop"),
            AuctionGroup(self.app),
            WishlistGroup(self.app),
            AdminGroup(self),
        ):
            self.tree.add_command(group)
        install_queries(self)

    async def setup_hook(self):
        await self.register()
        if self.app.settings.sync_commands:
            if self.app.settings.dev_guild_id:
                guild = discord.Object(id=self.app.settings.dev_guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            else:
                await self.tree.sync()
        self.jobs.start()

    async def on_ready(self):
        log.info("GumaBot ready as %s", self.user.id)

    async def command_error(self, interaction, error):
        error = getattr(error, "original", error)
        if isinstance(error, DomainError):
            message = str(error)
        elif isinstance(error, discord.app_commands.CheckFailure):
            message = "You do not have permission to use this command."
        else:
            log.error(
                "Interaction failed (%s)",
                type(error).__name__,
                exc_info=(type(error), error, error.__traceback__),
            )
            message = "Something went wrong. Any committed rewards remain saved; check your inventory or balance."
        try:
            await send(interaction, "GumaBot", message)
        except discord.HTTPException:
            log.warning("Could not deliver interaction error")

    async def on_interaction(self, i):
        if i.type == discord.InteractionType.application_command:
            log.info("Command %s by %s", (i.data or {}).get("name"), i.user.id)
            if i.guild_id:
                async with self.app.db.transaction() as tx:
                    if await tx.one("SELECT 1 FROM users WHERE discord_user_id=:u", u=i.user.id):
                        await tx.execute(
                            "INSERT INTO guilds(id) VALUES (:g) ON CONFLICT DO NOTHING",
                            g=i.guild_id,
                        )
                        await tx.execute(
                            "INSERT INTO guild_members VALUES (:g,:u) ON CONFLICT DO NOTHING",
                            g=i.guild_id,
                            u=i.user.id,
                        )
            return
        custom = (i.data or {}).get("custom_id", "")
        if i.type != discord.InteractionType.component or not custom.startswith("gb:"):
            return
        parts = custom.split(":")[1:]
        action = parts[0]
        try:
            if action == "guess":
                await i.response.send_modal(GuessModal(self.app, parts[1]))
                return
            await i.response.defer(ephemeral=True)
            cog = self.get_cog("GameCommands")
            if (
                action
                in (
                    "inventory",
                    "guide",
                    "close",
                    "dashboard",
                    "dash",
                    "journey",
                    "rank",
                    "sets",
                    "setpick",
                    "reveal",
                )
                and int(parts[1]) != i.user.id
            ):
                raise DomainError("This control belongs to another player.")
            if action == "close":
                await i.message.edit(view=None)
                await send(i, "GumaBot", "Closed.")
            elif action == "inventory":
                page = int(parts[2])
                await cog.show_inventory(i, await self.app.cards.inventory(i.user.id, page), page)
            elif action == "guide":
                await cog.guide_page(i, int(parts[2]))
            elif action == "dashboard":
                await cog.dashboard(i)
            elif action == "dash":
                kind = parts[2]
                if kind == "guide":
                    await cog.guide_page(i, 0)
                elif kind == "inventory":
                    await cog.show_inventory(i, await self.app.cards.inventory(i.user.id), 0)
                elif kind == "market":
                    await send(i, "Market", await self.app.market.browse())
                elif kind == "packs":
                    await show_sets(i, self.app)
                elif kind == "battle":
                    await send(i, "Battle", "Set /deck with five codes, then /duel or /gym.")
                else:
                    await send(i, kind.title(), await query(self.app, kind, i.user.id))
            elif action == "sets":
                await show_sets(i, self.app, int(parts[2]))
            elif action == "setpick":
                if int(parts[1]) != i.user.id:
                    raise DomainError("This control belongs to another player.")
                result = await self.app.cards.open_pack(i.user.id, i.data["values"][0], str(i.id))
                await send(
                    i,
                    "Your pack",
                    result,
                    buttons([("Reveal cards", f"reveal:{i.user.id}:{result['pack']}")]),
                )
            elif action == "reveal":
                await reveal_pack(i, self.app, parts[2])
            elif action == "buy":
                await self.app.market.buy(i.user.id, parts[1])
                await send(i, "Market", "Purchase completed.")
            elif action == "peek":
                await self.app.claims.claim_peek(i.user.id, parts[1])
                await send(i, "Pack Peek", "Card claimed.")
            elif action == "drop":
                await send(
                    i,
                    "Server drop",
                    await self.app.claims.claim_drop(i.user.id, parts[1], i.guild_id),
                )
            elif action == "trade":
                operation = {
                    "accept": self.app.trades.accept,
                    "confirm": self.app.trades.confirm,
                    "cancel": self.app.trades.cancel,
                }[parts[2]]
                await operation(i.user.id, parts[1])
                await cog.trade_info(i, parts[1])
            elif action == "duelaccept":
                await self.app.gameplay.accept_duel(i.user.id, parts[1])
                await show_duel(i, self.app, parts[1])
            elif action == "duel":
                await self.app.gameplay.duel_action(i.user.id, parts[1], parts[2], int(parts[3]))
                await show_duel(i, self.app, parts[1])
            elif action == "session":
                result = await self.app.gameplay.session_action(
                    i.user.id, parts[1], parts[2], int(parts[3])
                )
                if result["complete"]:
                    await send(i, "Game result", result)
                else:
                    await show_session(i, self.app, parts[1])
            elif action == "journey":
                await send(i, "Journey", await self.app.gameplay.journey(i.user.id, parts[2]))
            elif action == "rank":
                await send(
                    i,
                    "Leaderboard",
                    await self.app.progression.leaderboard(parts[2], int(parts[3])),
                )
            elif action == "sell":
                async with self.app.db.read() as tx:
                    preview = await self.app.cards.receipt(tx, i.user.id, parts[1], "sell_preview")
                if not preview or preview["due"] < self.app.clock.timestamp():
                    raise DomainError("Sale preview expired. Run /sell again.")
                amount = await self.app.market.sell(i.user.id, preview["codes"], "sell:" + parts[1])
                await send(i, "Sale", f"Received {amount} coins.")
        except Exception as exc:
            await self.command_error(i, exc)

    async def on_message(self, message):
        if not message.guild or message.author.bot or message.webhook_id:
            return
        now = time.monotonic()
        key = (message.guild.id, message.author.id)
        if self.activity_counts.get(key, 0) > now - 60:
            return
        if len(self.activity_counts) > 10000:
            self.activity_counts = {k: v for k, v in self.activity_counts.items() if v > now - 60}
        self.activity_counts[key] = now
        try:
            async with self.app.db.transaction() as tx:
                row = await tx.one(
                    "SELECT * FROM guilds WHERE id=:g AND drop_enabled=1", g=message.guild.id
                )
                if not row:
                    return
                await tx.execute(
                    "UPDATE guilds SET activity=activity+1 WHERE id=:g", g=message.guild.id
                )
                card = await tx.one("SELECT id FROM card_catalog ORDER BY id LIMIT 1")
            if row["activity"] >= 49 and card:
                drop = await self.app.claims.create_drop(message.guild.id, card["id"])
                channel = self.get_channel(row["drop_channel"])
                if channel:
                    await channel.send(
                        "GumaBot server drop — first claim wins!",
                        view=buttons([("Claim", f"drop:{drop}")]),
                    )
        except DomainError:
            pass
        except Exception:
            log.exception("Server activity handler failed")

    async def close(self):
        await self.jobs.close()
        await super().close()
