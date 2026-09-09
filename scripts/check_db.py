import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os

from dotenv import load_dotenv

from gumabot.database.migrations import check

if __name__ == "__main__":
    load_dotenv()
    path = Path(os.getenv("DATABASE_PATH", "data/gumabot.db"))
    if not path.exists():
        raise SystemExit("Database does not exist. Run py main.py --check first.")
    print(f"OK: integrity_check, foreign_key_check; schema version {check(path)}")
