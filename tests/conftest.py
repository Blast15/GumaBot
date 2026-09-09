import json
import random
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest_asyncio

from gumabot.database.db import Database
from gumabot.providers.tcgdex import TCGdexProvider
from gumabot.services.auctions import Auctions
from gumabot.services.cards import Cards
from gumabot.services.claims import Claims
from gumabot.services.economy import Economy
from gumabot.services.gameplay import Gameplay
from gumabot.services.grading import Grading
from gumabot.services.market import Market
from gumabot.services.progression import Progression
from gumabot.services.trades import Trades
from gumabot.utils.clock import Clock


class FakeClock(Clock):
    def __init__(self):
        self.value = 1788220800

    def now(self):
        return datetime.fromtimestamp(self.value, timezone.utc)

    def advance(self, seconds):
        self.value += seconds


@pytest_asyncio.fixture
async def app(tmp_path):
    clock = FakeClock()
    db = Database(tmp_path / "gumabot.db")
    await db.initialize()
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    provider = TCGdexProvider(client, db, clock)
    cards = Cards(db, clock, provider, random.Random(42))
    async with db.transaction() as tx:
        await tx.execute(
            "INSERT INTO card_sets VALUES ('test','Test',8,NULL,:t)", t=clock.timestamp()
        )
        for rarity in range(8):
            metadata = {
                "provider_id": f"test-{rarity}",
                "name": f"Card {rarity}",
                "set_id": "test",
                "set_name": "Test",
                "local_id": str(rarity),
                "rarity": [
                    "Common",
                    "Uncommon",
                    "Rare",
                    "Promo",
                    "Holo",
                    "Special",
                    "SIR",
                    "Mythical",
                ][rarity],
                "category": "Pokemon",
                "hp": 100,
                "types": ["Fire"],
                "image_url": None,
                "illustrator": None,
                "release_date": None,
                "raw_data": {},
            }
            await tx.execute(
                "INSERT INTO card_catalog VALUES (:id,:n,:search,'test',:r,:m)",
                id=f"test-{rarity}",
                n=f"Card {rarity}",
                search=f"card {rarity}",
                r=rarity,
                m=json.dumps(metadata),
            )
    result = SimpleNamespace(
        db=db,
        clock=clock,
        provider=provider,
        cards=cards,
        http=client,
        settings=SimpleNamespace(featured_set="test", topgg_bot_id="123", webhook_secret="x" * 32),
    )
    for name, cls in [("economy", Economy), ("claims", Claims), ("gameplay", Gameplay)]:
        setattr(result, name, cls(db, clock, cards, random.Random(42)))
    for name, cls in [
        ("market", Market),
        ("auctions", Auctions),
        ("grading", Grading),
        ("trades", Trades),
        ("progression", Progression),
    ]:
        setattr(result, name, cls(db, clock, random.Random(42)))
    yield result
    await provider.close()
    await client.aclose()
    await db.close()


async def users(app, count=2, coins=1000):
    async with app.db.transaction() as tx:
        for uid in range(1, count + 1):
            await tx.execute(
                "INSERT INTO users(discord_user_id,created_at,energy_updated_at) VALUES (:u,:t,:t)",
                u=uid,
                t=app.clock.timestamp(),
            )
            await app.cards.money(tx, uid, coins, "TEST", f"seed:{uid}")


async def mint(app, uid=1, card="test-0", score=50):
    async with app.db.transaction() as tx:
        return await app.cards.mint(tx, uid, card, "test", score)
