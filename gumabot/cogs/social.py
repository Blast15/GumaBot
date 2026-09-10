import discord
from discord import app_commands

from ..services.errors import DomainError
from ..views.ui import buttons, send
from .base import CommandBase


class SocialCommands(CommandBase):
    @app_commands.command(
        name="peek", description="Offer a spare duplicate for another player to claim"
    )
    async def peek(self, i: discord.Interaction, code: str):
        await self.defer(i)
        key = await self.app.claims.peek(i.user.id, code)
        await send(
            i,
            "Pack Peek",
            "One other player can claim this duplicate within ten minutes.",
            buttons([("Claim", f"peek:{key}")]),
            ephemeral=False,
        )

    @app_commands.command(
        name="trade", description="Invite, accept, inspect or update an escrow-backed trade"
    )
    async def trade(
        self,
        i: discord.Interaction,
        user: discord.User | None = None,
        action: str = "info",
        trade_id: str = "",
        kind: str = "card",
        reference: str = "",
        amount: int = 1,
    ):
        await self.defer(i)
        service = self.app.trades
        if user:
            if user.bot:
                raise DomainError("Choose a human player.")
            trade_id = await service.invite(i.user.id, user.id)
        elif action == "accept":
            await service.accept(i.user.id, trade_id)
        elif action == "add":
            await service.add(i.user.id, trade_id, kind, reference, amount)
        elif action == "confirm":
            await service.confirm(i.user.id, trade_id)
        elif action == "cancel":
            await service.cancel(i.user.id, trade_id)
        elif action != "info":
            raise DomainError("Actions: info, accept, add, confirm, cancel.")
        await self.trade_info(i, trade_id)

    async def trade_info(self, i, key):
        async with self.app.db.read() as tx:
            row = await tx.one(
                "SELECT * FROM trades WHERE id=:id AND (proposer=:u OR recipient=:u)",
                id=key,
                u=i.user.id,
            )
            items = (
                await tx.all(
                    "SELECT t.user_id,t.kind,CASE WHEN t.kind='card' THEN o.public_code ELSE t.reference END AS reference,t.amount FROM trade_items t LEFT JOIN owned_cards o ON t.kind='card' AND o.id=CAST(t.reference AS INTEGER) WHERE t.trade_id=:id",
                    id=key,
                )
                if row
                else []
            )
        if not row:
            raise DomainError("Trade not found.")
        await send(
            i,
            "Trade " + key,
            {"trade": row, "offers": items},
            buttons([(a.title(), f"trade:{key}:{a}") for a in ("accept", "confirm", "cancel")]),
            ephemeral=False,
        )
