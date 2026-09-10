import discord
from discord import app_commands

from ..services.errors import DomainError
from ..views.ui import buttons, send, show_duel, show_session
from .base import CommandBase


class GameplayCommands(CommandBase):
    @app_commands.command(
        name="deck",
        description="Set exactly five public codes separated by spaces, or view your deck",
    )
    async def deck(self, i: discord.Interaction, codes: str = ""):
        await self.defer(i)
        await send(
            i,
            "Deck",
            await self.app.gameplay.deck(i.user.id, codes.upper().split() if codes else None),
        )

    @app_commands.command(name="duel", description="Challenge a player or resume a persisted duel")
    async def duel(
        self, i: discord.Interaction, user: discord.User | None = None, duel_id: str = ""
    ):
        await self.defer(i)
        if user:
            if user.bot:
                raise DomainError("Choose a human player.")
            duel_id = await self.app.gameplay.invite_duel(i.user.id, user.id)
        await show_duel(i, self.app, duel_id)

    @app_commands.command(name="gym", description="Challenge one of eight original gym leaders")
    async def gym(self, i: discord.Interaction, leader: app_commands.Range[int, 1, 8] = 1):
        await self.defer(i)
        await send(i, "Gym", await self.app.gameplay.gym(i.user.id, leader))

    @app_commands.command(
        name="blackjack", description="Play blackjack with virtual coins only; maximum wager 500"
    )
    async def blackjack(self, i: discord.Interaction, wager: int = 10, session: str = ""):
        await self.defer(i)
        key = session or await self.app.gameplay.new_session(i.user.id, "blackjack", wager=wager)
        await show_session(i, self.app, key)

    @app_commands.command(
        name="quiz", description="Answer up to ten questions in a persisted session"
    )
    async def quiz(self, i: discord.Interaction, session: str = ""):
        await self.defer(i)
        key = session or await self.app.gameplay.new_session(i.user.id, "quiz")
        await show_session(i, self.app, key)

    @app_commands.command(
        name="pickcard", description="Choose one of up to three cards every thirty minutes"
    )
    async def pickcard(self, i: discord.Interaction, session: str = ""):
        await self.defer(i)
        key = session or await self.app.gameplay.new_session(
            i.user.id, "pickcard", self.app.settings.featured_set
        )
        await show_session(i, self.app, key)

    @app_commands.command(
        name="namepokemon", description="Identify a Pokémon from its provider image"
    )
    async def namepokemon(self, i: discord.Interaction, session: str = ""):
        await self.defer(i)
        key = session or await self.app.gameplay.new_session(
            i.user.id, "namepokemon", self.app.settings.featured_set
        )
        await show_session(i, self.app, key)

    @app_commands.command(name="journey", description="Explore encounters, rest or use a potion")
    async def journey(self, i: discord.Interaction, action: str = "explore"):
        await self.defer(i)
        await send(
            i,
            "Journey",
            await self.app.gameplay.journey(i.user.id, action),
            buttons(
                [(a.title(), f"journey:{i.user.id}:{a}") for a in ("explore", "rest", "potion")]
            ),
        )
