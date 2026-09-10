"""Opt-in login/guild/sync smoke; real interactions require the manual E2E protocol."""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import discord

from gumabot.app import Application
from gumabot.bot import GumaBot
from gumabot.config import Settings


async def smoke(channel_id: int):
    settings = Settings.load()
    if not settings.dev_guild_id:
        raise ValueError("DEV_GUILD_ID must identify a dedicated test guild")
    if settings.database == Path("data/gumabot.db"):
        raise ValueError("Set DATABASE_PATH to a dedicated test database")
    settings.sync_commands = False
    app = Application(settings)
    try:
        await app.initialize()
        async with GumaBot(app) as bot:
            await bot.login(settings.token)
            guild = await bot.fetch_guild(settings.dev_guild_id)
            channel = discord.utils.get(await guild.fetch_channels(), id=channel_id)
            if not isinstance(channel, discord.TextChannel):
                raise ValueError("Channel must be a text channel in DEV_GUILD_ID")
            member = await guild.fetch_member(bot.user.id)
            permissions = channel.permissions_for(member)
            required = (
                "view_channel",
                "send_messages",
                "embed_links",
                "attach_files",
                "read_message_history",
            )
            missing = [p for p in required if not getattr(permissions, p)]
            if missing:
                raise ValueError("Missing bot permissions: " + ", ".join(missing))
            bot.tree.copy_global_to(guild=guild)
            commands = await bot.tree.sync(guild=guild)
            names = {c.name for c in commands}
            if not {"start", "openpack", "trade", "market", "auction"} <= names:
                raise RuntimeError("Required commands are absent after guild sync")
            print("PASS: bot login, test guild access, channel permissions, guild command sync")
            print(
                "NOT TESTED: Gateway/reconnect, user interactions, global sync, restart/resume. See docs/OPERATIONS.md"
            )
    finally:
        await app.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel-id", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(smoke(args.channel_id))
