"""Official entry point: py main.py (or python main.py)."""

import argparse
import asyncio
import logging

from gumabot.app import Application
from gumabot.bot import GumaBot
from gumabot.config import Settings
from gumabot.jobs.webhook import Webhook
from gumabot.logging_config import configure


async def run(settings, check=False):
    app = Application(settings)
    webhook = Webhook(app)
    try:
        await app.initialize()
        async with GumaBot(app) as bot:
            if check:
                await bot.register()
                print(
                    f"OK: configuration, migrations, SQLite, game rules and {len(list(bot.tree.walk_commands()))} command entries. Discord connection not attempted."
                )
                return
            if settings.webhook_enabled:
                await webhook.start()
            await bot.start(settings.token, reconnect=True)
    finally:
        await webhook.close()
        await app.close()
        logging.getLogger(__name__).info("Shutdown complete")


def main():
    parser = argparse.ArgumentParser(description="GumaBot Discord card game")
    parser.add_argument(
        "--check", action="store_true", help="Validate local startup without connecting Discord"
    )
    args = parser.parse_args()
    try:
        settings = Settings.load()
        configure(settings.log_level)
        asyncio.run(run(settings, args.check))
    except KeyboardInterrupt:
        return 0
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1
    except Exception as exc:
        logging.getLogger(__name__).error(
            "Startup failed (%s). Check configuration and connectivity.", type(exc).__name__
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
