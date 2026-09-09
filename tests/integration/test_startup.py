import sqlite3

import pytest

from gumabot.app import Application
from gumabot.bot import GumaBot
from gumabot.config import Settings
from gumabot.database.migrations import MIGRATIONS, backup, check, migrate
from main import run


async def test_empty_startup_and_command_serialization(tmp_path):
    settings = Settings(token="test-only", database=tmp_path / "data" / "game.db")
    await run(settings, True)
    assert check(settings.database) == len(MIGRATIONS)
    app = Application(settings)
    try:
        await app.initialize()
        async with GumaBot(app) as bot:
            await bot.register()
            names = {c.qualified_name for c in bot.tree.walk_commands()}
            required = "start play guide help avatarchoice bag balance blackjack cardtrend checkgrade collection cooldowns daily deck duel duelprofile find fuse give grade gym inventory items itemshop buyitem journey leaderboard level missing mysterybox namepokemon openpack packs buypack resetpack pickcard quiz quizstats reminder report search sell serverleaderboard setchannel setcompletion showcase swapcodes tint trade upcoming wishlist market shop auction season".split()
            assert set(required) <= names
            assert "vote" not in names
            for command in bot.tree.get_commands():
                data = command.to_dict(bot.tree)
                assert data["name"] and data["description"]
    finally:
        await app.close()


def test_backup_and_sequential_migration(tmp_path):
    path = tmp_path / "test.db"
    migrate(path)
    migrate(path)
    assert check(path) == len(MIGRATIONS)
    saved = backup(path)
    assert check(saved) == len(MIGRATIONS)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("SELECT COUNT(*) FROM level_rewards").fetchone()[0] == 50
    with pytest.raises(ValueError):
        backup(tmp_path / "missing.db")


def test_migration_failure_rolls_back(tmp_path):
    path = tmp_path / "test.db"
    migrate(path)
    MIGRATIONS.append(["CREATE TABLE migration_probe(id INTEGER)", "INVALID SQL"])
    try:
        with pytest.raises(sqlite3.OperationalError):
            migrate(path)
        assert check(path) == len(MIGRATIONS) - 1
        with sqlite3.connect(path) as conn:
            assert not conn.execute(
                "SELECT name FROM sqlite_master WHERE name='migration_probe'"
            ).fetchall()
        assert list((tmp_path / "backups").glob("*.db"))
    finally:
        MIGRATIONS.pop()


@pytest.mark.parametrize(
    "change",
    [
        {"token": ""},
        {"api_base": "http://evil.test"},
        {"language": "../en"},
    ],
)
def test_config_validation(change):
    with pytest.raises(ValueError):
        Settings(**({"token": "test"} | change)).validate()


def test_backup_restore_scripts_and_config_load(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    path = tmp_path / "operational.db"
    migrate(path)
    environment = os.environ | {"DATABASE_PATH": str(path), "DISCORD_TOKEN": "local-check-only"}
    backed = subprocess.run(
        [sys.executable, "scripts/backup_db.py"],
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    source = backed.stdout.strip()
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO reports(user_id,body,created_at) VALUES (1,'test',1)")
    restored = subprocess.run(
        [sys.executable, "scripts/restore_db.py", source],
        input="RESTORE\n",
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "Restore complete" in restored.stdout
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0
    checked = subprocess.run(
        [sys.executable, "scripts/check_db.py"],
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "OK" in checked.stdout
    monkeypatch.setenv("DISCORD_TOKEN", "local-check-only")
    assert Settings.load().token == "local-check-only"
    monkeypatch.setenv("CARD_PROVIDER", "invalid")
    with pytest.raises(ValueError):
        Settings.load()
