import discord
from discord import app_commands

from ..services.errors import DomainError
from ..views.ui import buttons, send
from .base import CommandBase


class EconomyCommands(CommandBase):
    @app_commands.command(name="daily", description="Claim your rolling 24-hour daily reward")
    async def daily(self, i: discord.Interaction):
        await self.defer(i)
        await send(i, "Daily", f"Received {await self.app.economy.daily(i.user.id)} coins.")

    @app_commands.command(
        name="give", description="Transfer coins or an available card to another player"
    )
    async def give(
        self, i: discord.Interaction, user: discord.User, amount: int = 1, code: str = ""
    ):
        await self.defer(i)
        if user.bot:
            raise DomainError("Choose a human player.")
        await self.app.economy.give(i.user.id, user.id, amount, code, str(i.id))
        await send(i, "Gift", "Transfer completed.")

    @app_commands.command(name="buyitem", description="Purchase items using virtual coins")
    async def buyitem(self, i: discord.Interaction, item: str, quantity: int = 1):
        await self.defer(i)
        await self.app.economy.buy_item(i.user.id, item, quantity, str(i.id))
        await send(i, "Item shop", "Purchase completed.")

    @app_commands.command(name="buypack", description="Buy one energy for 40 coins")
    async def buypack(self, i: discord.Interaction):
        await self.defer(i)
        await self.app.economy.buy_pack(i.user.id, str(i.id))
        await send(i, "Packs", "Added one energy. Use /openpack.")

    @app_commands.command(
        name="resetpack", description="Compatibility alias: buy one energy for 40 coins"
    )
    async def resetpack(self, i: discord.Interaction):
        await self.defer(i)
        await self.app.economy.buy_pack(i.user.id, str(i.id))
        await send(i, "Packs", "Added one energy. Use /openpack.")

    @app_commands.command(name="mysterybox", description="Open a mystery box from your items")
    async def mysterybox(self, i: discord.Interaction):
        await self.defer(i)
        await send(
            i,
            "Mystery box",
            await self.app.economy.mystery_box(
                i.user.id, self.app.settings.featured_set, str(i.id)
            ),
        )

    @app_commands.command(
        name="sell", description="Preview a bulk sale of up to 25 unprotected raw cards"
    )
    async def sell(self, i: discord.Interaction):
        await self.defer(i)
        cards = await self.app.market.sell_preview(i.user.id)
        if not cards:
            raise DomainError("No eligible cards to sell.")
        key = self.app.cards.identifier()
        async with self.app.db.transaction() as tx:
            await self.app.cards.save_receipt(
                tx,
                i.user.id,
                key,
                "sell_preview",
                {
                    "codes": [c["public_code"] for c in cards],
                    "due": self.app.clock.timestamp() + 120,
                },
            )
        await send(
            i,
            "Confirm bulk sale",
            cards,
            buttons([("Confirm sale", f"sell:{key}"), ("Cancel", f"close:{i.user.id}")]),
        )

    @app_commands.command(
        name="cardtrend", description="View actual market sale statistics for 7 or 30 days"
    )
    async def cardtrend(self, i: discord.Interaction, card_id: str, days: int = 30):
        await self.defer(i)
        await send(i, "Price history", await self.app.market.trend(card_id, days))

    @app_commands.command(name="useitem", description="Use an energy booster or cosmetic badge")
    async def useitem(self, i: discord.Interaction, item: str):
        await self.defer(i)
        await self.app.economy.use_item(i.user.id, item, str(i.id))
        await send(i, "Items", "Item used.")
