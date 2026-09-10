import discord
from discord import app_commands

from ..services.errors import DomainError
from ..views.ui import ReportModal, buttons, send
from .base import CommandBase


class ProgressionCommands(CommandBase):
    @app_commands.command(name="reminder", description="Opt into or out of a personal reminder")
    async def reminder(self, i: discord.Interaction, kind: str, enabled: bool):
        await self.defer(i)
        await self.app.progression.reminder(i.user.id, kind, enabled)
        await send(i, "Reminders", "Preference saved.")

    @app_commands.command(name="report", description="Send bug feedback into the local database")
    async def report(self, i: discord.Interaction):
        await i.response.send_modal(ReportModal(self.app))

    @app_commands.command(
        name="avatarchoice", description="Choose your original GumaBot trainer avatar"
    )
    @app_commands.choices(
        avatar=[
            app_commands.Choice(name=x, value=x) for x in ("Scout", "Scholar", "Ranger", "Artisan")
        ]
    )
    async def avatarchoice(self, i: discord.Interaction, avatar: str):
        if avatar not in ("Scout", "Scholar", "Ranger", "Artisan"):
            raise DomainError("Invalid avatar.")
        await self.defer(i)
        async with self.app.db.transaction() as tx:
            await self.app.cards.user(tx, i.user.id)
            await tx.execute(
                "UPDATE users SET trainer_avatar=:a WHERE discord_user_id=:u", a=avatar, u=i.user.id
            )
        await send(i, "Trainer", avatar)

    @app_commands.command(name="setchannel", description="Configure server drops in a channel")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setchannel(
        self, i: discord.Interaction, channel: discord.TextChannel, enabled: bool = True
    ):
        if channel.guild.id != i.guild_id:
            raise DomainError("Choose a channel in this server.")
        await self.defer(i)
        async with self.app.db.transaction() as tx:
            await tx.execute(
                "INSERT INTO guilds(id,drop_channel,drop_enabled) VALUES (:g,:c,:e) ON CONFLICT(id) DO UPDATE SET drop_channel=:c,drop_enabled=:e",
                g=i.guild_id,
                c=channel.id,
                e=int(enabled),
            )
        await send(i, "Server drops", "Configuration saved.")

    @app_commands.command(
        name="leaderboard", description="Rank trainers by economy, collection or gameplay"
    )
    async def leaderboard(self, i: discord.Interaction, metric: str = "coins", page: int = 1):
        await self.defer(i)
        await send(
            i,
            "Leaderboard · " + metric,
            await self.app.progression.leaderboard(metric, page - 1),
            buttons(
                [
                    (x.title(), f"rank:{i.user.id}:{x}:0")
                    for x in (
                        "coins",
                        "aura",
                        "xp",
                        "collection",
                        "grades",
                        "duels",
                        "achievements",
                    )
                ]
            ),
        )
