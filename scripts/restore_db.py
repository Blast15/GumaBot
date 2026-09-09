"""Restore while GumaBot is stopped; uses SQLite's consistent backup mechanism."""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv

from gumabot.database.migrations import MIGRATIONS, backup, check

if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("backup_file", type=Path)
    args = parser.parse_args()
    source = args.backup_file
    if not source.is_file() or check(source) != len(MIGRATIONS):
        raise SystemExit("Backup is missing, invalid or has an incompatible schema.")
    destination = Path(os.getenv("DATABASE_PATH", "data/gumabot.db"))
    if source.resolve() == destination.resolve():
        raise SystemExit("Source and destination must differ.")
    if input("Stop GumaBot first. Type RESTORE to replace the database: ") != "RESTORE":
        raise SystemExit("Cancelled.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        print("Pre-restore backup:", backup(destination))
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    check(destination)
    print("Restore complete.")
