import asyncio
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from gumabot.database.db import Database
from gumabot.services.core import Service
from gumabot.services.errors import InsufficientFunds
from gumabot.utils.clock import Clock


@given(st.lists(st.integers(-200, 200), min_size=1, max_size=20))
@settings(max_examples=12, deadline=None)
def test_real_sqlite_balance_and_ledger_conservation(deltas):
    async def scenario(directory):
        db = Database(Path(directory) / "property.db")
        await db.initialize()
        service = Service(db, Clock())
        try:
            async with db.transaction() as tx:
                await tx.execute(
                    "INSERT INTO users(discord_user_id,created_at,energy_updated_at) VALUES (1,0,0)"
                )
            expected = 0
            for index, delta in enumerate(deltas):
                try:
                    async with db.transaction() as tx:
                        await service.money(tx, 1, delta, "PROPERTY", str(index))
                    expected += delta
                except InsufficientFunds:
                    assert expected + delta < 0
                async with db.read() as tx:
                    user = await service.user(tx, 1)
                    total = await tx.one(
                        "SELECT COALESCE(SUM(amount_delta),0) AS total FROM currency_ledger"
                    )
                    assert user["coins"] == expected == total["total"]
                    assert user["coins"] >= 0 and user["aura"] >= 0 and user["energy"] >= 0
        finally:
            await db.close()

    with tempfile.TemporaryDirectory() as directory:
        asyncio.run(scenario(directory))
