import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os

from dotenv import load_dotenv

from gumabot.database.migrations import backup

if __name__ == "__main__":
    load_dotenv()
    print(backup(Path(os.getenv("DATABASE_PATH", "data/gumabot.db"))))
