import sqlite3

import pytest
from conftest import users

from gumabot.database.migrations import MIGRATIONS, check, migrate
from gumabot.services.errors import DomainError


def test_upgrade_removes_retired_vote_schema_preserves_wallet_and_ledger(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        for migration in MIGRATIONS[:3]:
            for statement in migration:
                conn.execute(statement)
        conn.execute("PRAGMA user_version=3")
        conn.execute(
            "INSERT INTO users(discord_user_id,created_at,energy_updated_at,coins,vote_streak,last_vote_at) VALUES (1,0,0,90,1,100)"
        )
        conn.execute(
            "INSERT INTO currency_ledger(user_id,currency,amount_delta,reason,correlation_id,created_at) VALUES (1,'coins',90,'VOTE','legacy',100)"
        )
        conn.execute("INSERT INTO vote_events VALUES ('old-event',1,100)")
        conn.execute("INSERT INTO vote_inbox VALUES ('pending',1,100,'pending')")
        conn.execute("INSERT INTO cooldowns VALUES (1,'vote',1000)")
        conn.execute("INSERT INTO cooldowns VALUES (1,'daily',1000)")
        conn.execute("INSERT INTO reminder_preferences VALUES (1,'vote',1,0)")
        conn.execute("INSERT INTO reminder_preferences VALUES (1,'daily',1,0)")
    migrate(path)
    migrate(path)
    assert check(path) == 4
    with sqlite3.connect(path) as conn:
        assert not conn.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'vote_%'"
        ).fetchall()
        columns = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
        assert not {"vote_streak", "last_vote_at"} & columns
        assert conn.execute("SELECT coins FROM users").fetchone()[0] == 90
        assert conn.execute("SELECT amount_delta,reason FROM currency_ledger").fetchone() == (
            90,
            "VOTE",
        )
        assert conn.execute("SELECT kind FROM cooldowns").fetchall() == [("daily",)]
        assert conn.execute("SELECT kind FROM reminder_preferences").fetchall() == [("daily",)]
    assert list((tmp_path / "backups").glob("*.db"))


async def test_vote_reminder_no_longer_accepted(app):
    await users(app, 1)
    with pytest.raises(DomainError):
        await app.progression.reminder(1, "vote", True)
    assert not hasattr(app.economy, "verified_vote")
