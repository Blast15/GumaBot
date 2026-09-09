import asyncio

from conftest import mint, users

from gumabot.services.errors import DomainError


async def race(calls):
    results = await asyncio.gather(*calls, return_exceptions=True)
    for result in results:
        assert not isinstance(result, BaseException) or isinstance(result, DomainError), repr(
            result
        )
    return [r for r in results if not isinstance(r, BaseException)]


async def test_start_twenty(app):
    await asyncio.gather(*(app.cards.start(1, "test") for _ in range(20)))
    async with app.db.read() as tx:
        assert (await tx.one("SELECT COUNT(*) AS n FROM owned_cards"))["n"] == 5
        assert (
            await tx.one("SELECT COUNT(*) AS n FROM currency_ledger WHERE reason='START_REWARD'")
        )["n"] == 1


async def test_daily_twenty(app):
    await users(app, 1)
    assert len(await race([app.economy.daily(1) for _ in range(20)])) == 1
    async with app.db.read() as tx:
        assert (await tx.one("SELECT COUNT(*) AS n FROM currency_ledger WHERE reason='DAILY'"))[
            "n"
        ] == 1


async def test_market_twenty(app):
    await users(app, 21)
    code = await mint(app)
    listing = await app.market.list_card(1, code, 100)
    assert len(await race([app.market.buy(uid, listing) for uid in range(2, 22)])) == 1
    async with app.db.read() as tx:
        assert (await tx.one("SELECT COUNT(*) AS n FROM market_sales"))["n"] == 1
        assert (
            await tx.one("SELECT COUNT(*) AS n FROM currency_ledger WHERE reason='MARKET_SALE'")
        )["n"] == 1
        owner = (await tx.one("SELECT owner_id FROM owned_cards WHERE public_code=:c", c=code))[
            "owner_id"
        ]
        assert owner != 1


async def test_peek_twenty(app):
    await users(app, 21)
    code = await mint(app)
    await mint(app)
    key = await app.claims.peek(1, code)
    assert len(await race([app.claims.claim_peek(u, key) for u in range(2, 22)])) == 1
    async with app.db.read() as tx:
        assert (await tx.one("SELECT COUNT(*) AS n FROM pack_peek_claims"))["n"] == 1


async def test_drop_twenty(app):
    await users(app, 20)
    async with app.db.transaction() as tx:
        await tx.execute("INSERT INTO guilds(id,drop_enabled) VALUES (123,1)")
    key = await app.claims.create_drop(123, "test-0")
    assert len(await race([app.claims.claim_drop(u, key, 123) for u in range(1, 21)])) == 1
    async with app.db.read() as tx:
        assert (await tx.one("SELECT COUNT(*) AS n FROM owned_cards"))["n"] == 1


async def test_grade_two_workers(app):
    await users(app, 1)
    code = await mint(app)
    await app.grading.submit(1, code)
    app.clock.advance(432001)
    assert sum(await asyncio.gather(app.grading.complete_due(), app.grading.complete_due())) == 1
    async with app.db.read() as tx:
        assert (await tx.one("SELECT COUNT(*) AS n FROM grade_certificates"))["n"] == 1


async def test_auction_two_workers(app):
    await users(app)
    key = await app.auctions.create(1, await mint(app), 50, 1)
    await app.auctions.bid(2, key, 50)
    app.clock.advance(3601)
    assert sum(await asyncio.gather(app.auctions.settle_due(), app.auctions.settle_due())) == 1
    async with app.db.read() as tx:
        assert (await tx.one("SELECT COUNT(*) AS n FROM price_history"))["n"] == 1
        assert not await tx.all("SELECT * FROM auction_holds")


async def test_season_two_workers(app):
    await users(app)
    await app.economy.daily(1)
    app.clock.advance(32 * 86400)
    assert sum(await asyncio.gather(app.progression.rollover(), app.progression.rollover())) == 1
    async with app.db.read() as tx:
        assert (await tx.one("SELECT COUNT(*) AS n FROM hall_of_fame"))["n"] == 1


async def test_pack_retry_and_energy_race(app):
    await users(app, 1)
    results = await asyncio.gather(*(app.cards.open_pack(1, "test", "same") for _ in range(20)))
    assert all(r == results[0] for r in results)
    assert (await app.economy.balance(1))["energy"] == 2
    assert len(await race([app.cards.open_pack(1, "test", str(i)) for i in range(20)])) == 2


async def test_trade_confirmation_race(app):
    await users(app)
    code = await mint(app)
    key = await app.trades.invite(1, 2)
    await app.trades.accept(2, key)
    await app.trades.add(1, key, "card", code)
    await app.trades.add(2, key, "coins", amount=30)
    await app.trades.confirm(1, key)
    assert len(await race([app.trades.confirm(2, key) for _ in range(20)])) == 1
    assert (await app.economy.balance(1))["coins"] == 1030
