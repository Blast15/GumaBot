import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure(level: str):
    Path("logs").mkdir(exist_ok=True)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(
                "logs/gumabot.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
            ),
        ],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
