import asyncio
import json

import pytest
from conftest import mint, users
from sqlalchemy.exc import IntegrityError

from gumabot.cogs.queries import query
from gumabot.services.engines import QUESTIONS
from gumabot.services.errors import DomainError


async def test_currency_ledger_immutable_and_rollback(app):
    await users(app)
    with pytest.raises(IntegrityError):
        async with app.db.transaction() as tx:
            await tx.execute("UPDATE currency_ledger SET amount_delta=999")
    with pytest.raises(IntegrityError):
        async with app.db.transaction() as tx:
            await tx.execute("DELETE FROM currency_ledger")
    with pytest.raises(DomainError):
        await app.economy.give(1, 2, 1001, "", "give")
    assert (await app.economy.balance(1))["coins"] == 1000
    assert (await app.economy.balance(2))["coins"] == 1000
    for amount in (-1, 0, 1.5, True):
        with pytest.raises(DomainError):
            await app.economy.give(1, 2, amount, "", "bad")
    with pytest.raises(DomainError):
        await app.economy.give(1, 1, 1, "", "self")
    await app.economy.give(1, 2, 100, "", "give")
    await app.economy.give(1, 2, 100, "", "give")
    assert (await app.economy.balance(1))["coins"] == 900
    code = await mint(app)
    await app.economy.give(1, 2, 0, code, "card")
    assert (await app.cards.search(2, code))["owner_id"] == 2


async def test_items_boxes_energy_and_vote(app):
    await users(app, 1, 10000)
    await app.economy.buy_item(1, "box", 30, "box-buy")
    await app.economy.buy_item(1, "box", 30, "box-buy")
    results = [await app.economy.mystery_box(1, "test", str(i)) for i in range(30)]
    assert {"card", "coins", "aura", "item"} <= {next(iter(r)) for r in results}
    assert await app.economy.mystery_box(1, "test", "0") == results[0]
    await app.economy.buy_pack(1, "energy")
    await app.economy.buy_pack(1, "energy")
    assert (await app.economy.balance(1))["energy"] == 4
    await app.economy.verified_vote(1, "vote-event", "test")
    assert (await app.economy.balance(1))["energy"] == 6
    with pytest.raises(DomainError):
        await app.economy.verified_vote(1, "vote-event", "test")
    with pytest.raises(DomainError):
        await app.economy.verified_vote(1, "new-vote", "test")
    app.clock.advance(43200)
    await app.economy.verified_vote(1, "second-vote", "test")
    assert (await app.economy.balance(1))["vote_streak"] == 2
    with pytest.raises(DomainError):
        await app.economy.buy_item(1, "bad", 1, "bad")


async def test_fusion_locks_tint_codes_inventory(app):
    await users(app)
    codes = [await mint(app, score=s) for s in (10, 50, 90)]
    await app.cards.swap_codes(1, codes[0], codes[1])
    assert (await app.cards.search(1, codes[0]))["condition_score"] == 50
    with pytest.raises(DomainError):
        await app.cards.swap_codes(1, codes[0], codes[0])
    with pytest.raises(DomainError):
        await app.cards.fuse(1, [codes[0]] * 3)
    with pytest.raises(DomainError):
        await app.cards.fuse(2, codes)
    await app.economy.buy_item(1, "tint", 1, "tint")
    await app.cards.tint(1, codes[0], "#336699")
    with pytest.raises(DomainError):
        await app.cards.tint(1, codes[0], "bad")
    new = await app.cards.fuse(1, codes)
    assert (await app.cards.search(1, new))["condition_score"] == 100
    rows = await app.cards.inventory(1)
    assert len(rows) == 1
    for sort in ("oldest", "rarity", "condition", "grade", "set"):
        assert len(await app.cards.inventory(1, sort=sort)) == 1
    assert (
        len(
            await app.cards.inventory(
                1, name="CARD", set_id="test", rarity=0, condition_name="Pristine", graded=False
            )
        )
        == 1
    )
    with pytest.raises(DomainError):
        await app.cards.inventory(1, sort="DROP TABLE")
    with pytest.raises(DomainError):
        await app.cards.search(2, new)
    with pytest.raises(DomainError):
        await app.market.list_card(1, codes[0], 10)


async def test_market_cancel_failure_and_sale_protection(app):
    await users(app)
    code = await mint(app)
    listing = await app.market.list_card(1, code, 1001)
    assert len(await app.market.browse()) == 1
    with pytest.raises(DomainError):
        await app.market.buy(2, listing)
    with pytest.raises(DomainError):
        await app.market.buy(1, listing)
    with pytest.raises(DomainError):
        await app.market.remove(2, listing)
    await app.market.remove(1, listing)
    assert not await app.market.browse()
    listing = await app.market.list_card(1, code, 100)
    await app.market.buy(2, listing)
    stats = await app.market.trend("test-0", 7)
    assert stats["median"] == 100 and stats["volume"] == 1
    with pytest.raises(DomainError):
        await app.market.trend("test-0", 1)
    with pytest.raises(IntegrityError):
        async with app.db.transaction() as tx:
            await tx.execute("DELETE FROM price_history")
    await mint(app, 2, "test-4")
    preview = await app.market.sell_preview(2)
    assert len(preview) == 1
    assert await app.market.sell(2, [code], "sale") == 5
    assert await app.market.sell(2, [code], "sale") == 5


async def test_auction_escrow_outbid_cancel_buyout(app):
    await users(app, 3)
    code = await mint(app)
    key = await app.auctions.create(1, code, 100, buyout=200)
    await app.auctions.bid(2, key, 100)
    assert (await app.economy.balance(2))["coins"] == 900
    with pytest.raises(DomainError):
        await app.economy.give(2, 3, 901, "", "overspend")
    with pytest.raises(DomainError):
        await app.auctions.bid(3, key, 104)
    await app.auctions.bid(3, key, 105)
    assert (await app.economy.balance(2))["coins"] == 1000
    with pytest.raises(DomainError):
        await app.auctions.cancel(1, key)
    await app.auctions.bid(2, key, 200)
    assert (await app.cards.search(2, code))["owner_id"] == 2
    assert (await app.economy.balance(3))["coins"] == 1000
    assert (await app.economy.balance(1))["coins"] == 1200
    key = await app.auctions.create(1, await mint(app), 10)
    await app.auctions.cancel(1, key)
    key = await app.auctions.create(1, await mint(app), 10, 1)
    app.clock.advance(3601)
    assert await app.auctions.settle_due() == 1


async def test_trade_mutation_resets_and_expiry_refunds(app):
    await users(app)
    key = await app.trades.invite(1, 2)
    with pytest.raises(DomainError):
        await app.trades.add(1, key, "coins", amount=10)
    with pytest.raises(DomainError):
        await app.trades.accept(1, key)
    await app.trades.accept(2, key)
    await app.economy.buy_item(1, "tint", 2, "tint-buy")
    await app.trades.add(1, key, "item", "tint", 2)
    await app.trades.add(1, key, "coins", amount=50)
    await app.trades.confirm(1, key)
    await app.trades.add(2, key, "coins", amount=20)
    assert await app.trades.confirm(2, key) == "Waiting for the other player."
    app.clock.advance(1801)
    await asyncio.gather(app.trades.expire(), app.trades.expire())
    assert (await app.economy.balance(1))["coins"] == 940
    assert (await app.economy.balance(2))["coins"] == 1000
    async with app.db.read() as tx:
        assert (await tx.one("SELECT quantity FROM user_items WHERE user_id=1 AND item_id='tint'"))[
            "quantity"
        ] == 2
    key = await app.trades.invite(1, 2)
    await app.trades.cancel(1, key)


async def test_grading_and_claim_expiry(app):
    await users(app)
    code = await mint(app)
    await mint(app)
    key = await app.claims.peek(1, code)
    with pytest.raises(DomainError):
        await app.claims.claim_peek(1, key)
    app.clock.advance(601)
    await app.claims.expire()
    with pytest.raises(DomainError):
        await app.claims.claim_peek(2, key)
    await app.economy.buy_item(1, "coupon", 1, "coupon")
    job = await app.grading.submit(1, code, "express", True)
    assert job["fee"] == 150
    assert (await app.grading.check(1, code))["grade_status"] == "pending"
    with pytest.raises(DomainError):
        await app.economy.give(1, 2, 0, code, "locked")
    app.clock.advance(21600)
    await app.grading.complete_due()
    cert = await app.grading.check(1, code)
    assert cert["certificate"].startswith("GUMA-CERT-") and cert["population"] == 1
    with pytest.raises(DomainError):
        await app.grading.submit(1, code)


async def test_game_sessions_and_quiz_stats(app):
    await users(app)
    key = await app.gameplay.new_session(1, "quiz")
    for pos in range(10):
        async with app.db.read() as tx:
            row = await tx.one("SELECT state FROM quiz_attempts WHERE id=:id", id=key)
        state = json.loads(row["state"])
        answer = QUESTIONS[state["order"][pos]][2]
        result = await app.gameplay.session_action(1, key, str(answer), pos)
    assert result["complete"] and result["score"] == 10
    with pytest.raises(DomainError):
        await app.gameplay.session_action(1, key, "0", 0)
    stats = await query(app, "quizstats", 1)
    assert stats["correct"] == 10 and stats["best_streak"] == 10
    key = await app.gameplay.new_session(1, "pickcard", "test")
    result = await app.gameplay.session_action(1, key, "1")
    assert result["card"].startswith("GUMA-")
    key = await app.gameplay.new_session(1, "namepokemon", "test")
    result = await app.gameplay.session_action(1, key, "wrong")
    assert not result["correct"]
    key = await app.gameplay.new_session(1, "blackjack", wager=50)
    result = await app.gameplay.session_action(1, key, "stand", 2)
    assert result["complete"] and result["payout"] in (0, 50, 100)


async def test_deck_duel_gym_and_expiry(app):
    await users(app)
    for uid in (1, 2):
        codes = [await mint(app, uid, "test-7" if uid == 1 else "test-0") for _ in range(5)]
        await app.gameplay.deck(uid, codes)
    key = await app.gameplay.invite_duel(1, 2)
    await app.gameplay.accept_duel(2, key)
    for turn in range(60):
        state = await app.gameplay.duel_action(1 if turn % 2 == 0 else 2, key, "attack", turn)
        if state["winner"] is not None:
            break
    assert state["winner"] == 0
    assert (await query(app, "duelprofile", 1))["wins"] == 1
    gym = await app.gameplay.gym(1, 1)
    assert gym["won"]
    with pytest.raises(DomainError):
        await app.gameplay.gym(1, 3)
    app.clock.advance(1801)
    key = await app.gameplay.invite_duel(1, 2)
    await app.gameplay.accept_duel(2, key)
    app.clock.advance(1801)
    await app.gameplay.expire()
    assert len(await app.gameplay.deck(1)) == 5


async def test_journey_rewards_and_bag(app):
    await users(app, 1)
    for _ in range(15):
        app.clock.advance(301)
        result = await app.gameplay.journey(1)
        if result["hp"] < 20:
            app.clock.advance(301)
            await app.gameplay.journey(1, "rest")
    assert result["stage"] >= 5
    async with app.db.transaction() as tx:
        await tx.execute(
            "INSERT INTO journey_inventory VALUES (1,'potion',1) ON CONFLICT(user_id,item) DO UPDATE SET quantity=1"
        )
    await app.gameplay.journey(1, "potion")
    with pytest.raises(DomainError):
        await app.gameplay.journey(1, "potion")
    with pytest.raises(DomainError):
        await app.gameplay.journey(1, "invalid")


async def test_progression_levels_quests_queries(app):
    await users(app)
    async with app.db.transaction() as tx:
        await app.cards.event(tx, 1, "collection", 300000)
        for _ in range(10):
            await app.cards.event(tx, 1, "pack", 0)
    assert (await app.economy.balance(1))["level"] == 50
    assert len(await app.progression.quests(1)) == 3
    for metric in ("coins", "aura", "xp", "collection", "grades", "duels", "achievements"):
        assert len(await app.progression.leaderboard(metric)) == 2
    for name in (
        "balance",
        "level",
        "collection",
        "setcompletion",
        "missing",
        "items",
        "itemshop",
        "bag",
        "quizstats",
        "duelprofile",
        "achievements",
        "quests",
        "season",
        "serverleaderboard",
        "cooldowns",
        "upcoming",
    ):
        await query(app, name, 1)
    await app.progression.reminder(1, "daily", True)
    await app.progression.reminder(1, "daily", False)
    with pytest.raises(DomainError):
        await app.progression.reminder(1, "bad", True)
    await app.progression.report(1, "This is a sufficiently long report.")
    with pytest.raises(DomainError):
        await app.progression.report(1, "short")


async def test_use_items_and_item_trade_settlement(app):
    await users(app)
    await app.economy.buy_item(1, "booster", 1, "booster")
    await app.economy.use_item(1, "booster", "use")
    await app.economy.use_item(1, "booster", "use")
    assert (await app.economy.balance(1))["energy"] == 4
    await app.economy.buy_item(1, "cosmetic", 1, "cosmetic")
    await app.economy.use_item(1, "cosmetic", "wear")
    assert (await app.economy.balance(1))["trainer_avatar"].endswith("★")
    with pytest.raises(DomainError):
        await app.economy.use_item(1, "tint", "bad")
    await app.economy.buy_item(1, "tint", 1, "tint")
    trade = await app.trades.invite(1, 2)
    await app.trades.accept(2, trade)
    await app.trades.add(1, trade, "item", "tint", 1)
    await app.trades.confirm(1, trade)
    assert await app.trades.confirm(2, trade) == "Trade completed."
    async with app.db.read() as tx:
        assert (await tx.one("SELECT quantity FROM user_items WHERE user_id=2 AND item_id='tint'"))[
            "quantity"
        ] == 1
