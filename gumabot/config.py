import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    token: str = field(repr=False, default="")
    database: Path = Path("data/gumabot.db")
    log_level: str = "INFO"
    api_base: str = "https://api.tcgdex.net/v2/en"
    language: str = "en"
    featured_set: str = "base1"
    sync_commands: bool = True
    dev_guild_id: int | None = None
    topgg_bot_id: str = ""
    webhook_secret: str = field(repr=False, default="")
    webhook_enabled: bool = False
    webhook_version: str = "v1"
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080

    @classmethod
    def load(cls):
        load_dotenv()
        e = os.environ
        if e.get("CARD_PROVIDER", "tcgdex") != "tcgdex":
            raise ValueError("CARD_PROVIDER must be tcgdex")
        settings = cls(
            token=e.get("DISCORD_TOKEN", ""),
            database=Path(e.get("DATABASE_PATH", "data/gumabot.db")),
            log_level=e.get("LOG_LEVEL", "INFO").upper(),
            api_base=e.get("CARD_API_BASE", "https://api.tcgdex.net/v2/en"),
            language=e.get("CARD_API_LANGUAGE", "en"),
            featured_set=e.get("FEATURED_SET", "base1"),
            sync_commands=e.get("SYNC_COMMANDS_ON_START", "true").lower() == "true",
            dev_guild_id=int(e["DEV_GUILD_ID"]) if e.get("DEV_GUILD_ID") else None,
            topgg_bot_id=e.get("TOPGG_BOT_ID", ""),
            webhook_secret=e.get("TOPGG_WEBHOOK_SECRET", ""),
            webhook_enabled=e.get("ENABLE_TOPGG_WEBHOOK", "false").lower() == "true",
            webhook_version=e.get("TOPGG_WEBHOOK_VERSION", "v1"),
            webhook_host=e.get("WEBHOOK_HOST", "0.0.0.0"),
            webhook_port=int(e.get("WEBHOOK_PORT", "8080")),
        )
        settings.validate()
        return settings

    def validate(self):
        if not self.token:
            raise ValueError(
                "DISCORD_TOKEN is missing. Copy .env.example to .env and insert your Discord bot token."
            )
        parsed = urlparse(self.api_base)
        if parsed.scheme != "https" or parsed.hostname != "api.tcgdex.net":
            raise ValueError("CARD_API_BASE must use https://api.tcgdex.net")
        if not self.language.isalpha() or len(self.language) != 2:
            raise ValueError("CARD_API_LANGUAGE must be a two-letter language code")
        if self.webhook_enabled and len(self.webhook_secret) < 32:
            raise ValueError("TOPGG_WEBHOOK_SECRET must have at least 32 characters")
        if self.webhook_version not in ("v0", "v1"):
            raise ValueError("TOPGG_WEBHOOK_VERSION must be v0 or v1")
        if not 1 <= self.webhook_port <= 65535:
            raise ValueError("Invalid WEBHOOK_PORT")
