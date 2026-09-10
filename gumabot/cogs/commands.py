import discord
from discord import app_commands

from ..views.ui import GUIDE, buttons, send
from .collection import CollectionCommands
from .economy import EconomyCommands
from .gameplay import GameplayCommands
from .progression import ProgressionCommands
from .social import SocialCommands


class GameCommands(
    CollectionCommands, EconomyCommands, SocialCommands, GameplayCommands, ProgressionCommands
):
    @app_commands.command(name="play", description="Open your trainer dashboard")
    async def play(self, i: discord.Interaction):
        await self.defer(i)
        await self.dashboard(i)

    async def dashboard(self, i):
        user = await self.app.economy.balance(i.user.id)
        await send(
            i,
            "GumaBot",
            {k: user[k] for k in ("coins", "aura", "xp", "level", "energy", "energy_updated_at")}
            | {"featured_set": self.app.settings.featured_set, "daily": "/daily"},
            buttons(
                [
                    (x.title(), f"dash:{i.user.id}:{x}")
                    for x in (
                        "packs",
                        "inventory",
                        "collection",
                        "market",
                        "battle",
                        "quests",
                        "guide",
                    )
                ]
            ),
        )

    @app_commands.command(name="guide", description="Seven-page GumaBot tutorial")
    async def guide(self, i: discord.Interaction):
        await self.guide_page(i, 0)

    async def guide_page(self, i, page):
        page = max(0, min(6, page))
        await send(
            i,
            f"Guide {page + 1}/7",
            GUIDE[page],
            buttons(
                [
                    ("Previous", f"guide:{i.user.id}:{max(0, page - 1)}"),
                    ("Next", f"guide:{i.user.id}:{min(6, page + 1)}"),
                    ("Close", f"close:{i.user.id}"),
                ]
            ),
        )

    @app_commands.command(
        name="help", description="List the commands actually registered in this bot"
    )
    async def help(self, i: discord.Interaction):
        names = sorted(
            "/" + c.qualified_name
            for c in self.bot.tree.walk_commands()
            if not isinstance(c, app_commands.Group)
        )
        await send(i, "GumaBot commands", "\n".join(names))
