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
