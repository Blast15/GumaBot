import asyncio
import json
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from conftest import users

from gumabot.jobs.manager import Jobs
from gumabot.services.core import Service
from gumabot.services.errors import DomainError
from gumabot.services.quiz import build_questions, question_at


def bot_for(app, send):
    user = SimpleNamespace(send=send)
    return SimpleNamespace(
        app=app, get_user=lambda uid: user, fetch_user=AsyncMock(return_value=user)
    )


async def ready_reminder(app):
    await users(app, 1)
    await app.progression.reminder(1, "daily", True)
    async with app.db.transaction() as tx:
        await tx.execute("INSERT INTO cooldowns VALUES (1,'daily',:t)", t=app.clock.timestamp() - 1)


async def delivery(app):
    async with app.db.read() as tx:
        return await tx.one(
            "SELECT d.*,p.last_sent FROM reminder_deliveries d JOIN reminder_preferences p USING(user_id,kind)"
        )


async def test_reminder_retries_after_failure_and_restart(app):
    await ready_reminder(app)
    send = AsyncMock(side_effect=[OSError("offline"), None])
    bot = bot_for(app, send)
    await Jobs(bot).reminders()
    row = await delivery(app)
    assert row["status"] == "pending" and row["last_sent"] == 0 and row["attempts"] == 1
    await Jobs(bot).reminders()
    assert send.call_count == 1
    app.clock.advance(60)
    await Jobs(bot).reminders()
    row = await delivery(app)
    assert row["status"] == "sent" and row["last_sent"] == row["due_at"]
    app.clock.advance(3601)
    await Jobs(bot).reminders()
    assert send.call_count == 2


async def test_reminder_race_single_claim(app):
    await ready_reminder(app)
    send = AsyncMock()
    bot = bot_for(app, send)
    await asyncio.gather(Jobs(bot).reminders(), Jobs(bot).reminders())
    assert send.call_count == 1


async def test_reminder_recovers_abandoned_claim_and_opt_out(app):
    await ready_reminder(app)
    bot = bot_for(app, AsyncMock())
    jobs = Jobs(bot)
    await jobs.reminder_worker.enqueue()
    async with app.db.transaction() as tx:
        await tx.execute(
            "UPDATE reminder_deliveries SET status='claimed',attempts=1,next_attempt_at=:t,claim_token='old'",
            t=app.clock.timestamp() + 120,
        )
    await jobs.reminders()
    assert bot.get_user(1).send.call_count == 0
    app.clock.advance(121)
    await app.progression.reminder(1, "daily", False)
    await jobs.reminders()
    assert bot.get_user(1).send.call_count == 0
    await app.progression.reminder(1, "daily", True)
    await jobs.reminders()
    assert (await delivery(app))["status"] == "sent"


@pytest.mark.parametrize("permanent", [True, False])
async def test_reminder_terminal_failure(app, permanent):
    await ready_reminder(app)
    error = (
        discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "DMs disabled")
        if permanent
        else OSError("offline")
    )
    send = AsyncMock(side_effect=error)
    jobs = Jobs(bot_for(app, send))
    for _ in range(8):
        await jobs.reminders()
        app.clock.advance(3601)
    row = await delivery(app)
    assert row["status"] == "failed" and row["last_sent"] == 0
    assert send.call_count == (1 if permanent else 5)


async def test_reminder_scan_does_not_starve_later_rows(app):
    await users(app, 101)
    async with app.db.transaction() as tx:
        for uid in range(1, 102):
            await tx.execute(
                "INSERT INTO reminder_preferences(user_id,kind,enabled) VALUES (:u,'daily',1)",
                u=uid,
            )
        await tx.execute(
            "INSERT INTO cooldowns VALUES (101,'daily',:t)", t=app.clock.timestamp() - 1
        )
    send = AsyncMock()
    jobs = Jobs(bot_for(app, send))
    await jobs.reminders()
    assert send.call_count == 0
    await jobs.reminders()
    assert send.call_count == 1


@pytest.mark.parametrize("size", [1, 2, 3, 8])
async def test_pickcard_unique_small_pools_and_invalid_button(app, size):
    await users(app, 1)
    async with app.db.read() as tx:
        pool = await tx.all("SELECT * FROM card_catalog ORDER BY id LIMIT :n", n=size)
    app.cards.ensure_set = AsyncMock(return_value=pool)
    key = await app.gameplay.new_session(1, "pickcard", "test")
    async with app.db.read() as tx:
        state = json.loads(
            (await tx.one("SELECT state FROM quiz_attempts WHERE id=:id", id=key))["state"]
        )
    assert len(set(state["choices"])) == min(3, size)
    with pytest.raises(DomainError):
        await app.gameplay.session_action(1, key, str(len(state["choices"])))
    await app.gameplay.session_action(1, key, "0")


async def test_drop_uses_weighted_catalog_and_keeps_cooldown(app):
    async with app.db.transaction() as tx:
        await tx.execute("INSERT INTO guilds(id,drop_enabled) VALUES (1,1)")
    seen = set()
    for _ in range(30):
        key = await app.claims.create_drop(1)
        async with app.db.read() as tx:
            seen.add(
                (await tx.one("SELECT card_id FROM server_drops WHERE id=:id", id=key))["card_id"]
            )
        with pytest.raises(DomainError):
            await app.claims.create_drop(1)
        app.clock.advance(3601)
    assert len(seen) >= 3


async def test_quiz_snapshot_survives_catalog_change(app):
    await users(app, 1)
    key = await app.gameplay.new_session(1, "quiz")
    async with app.db.transaction() as tx:
        state = json.loads(
            (await tx.one("SELECT state FROM quiz_attempts WHERE id=:id", id=key))["state"]
        )
        await tx.execute("UPDATE card_catalog SET metadata='{}'")
    assert len(state["questions"]) == 10
    assert any("test-" in q[0] for q in state["questions"])
    for pos in range(10):
        result = await app.gameplay.session_action(1, key, question_at(state, pos)[2], pos)
    assert result["complete"] and result["score"] == 10


def test_catalog_quiz_diversity_and_legacy_fallback():
    rows = [
        {
            "id": str(i),
            "name": f"Card {i}",
            "metadata": json.dumps(
                {"hp": 10 + i, "set_name": f"Set {i % 4}", "illustrator": f"Artist {i % 5}"}
            ),
        }
        for i in range(300)
    ]
    seen = set()
    for seed in range(80):
        for prompt, options, answer in build_questions(rows, random.Random(seed)):
            assert len(options) == len(set(options)) == 3
            assert 0 <= answer < 3
            seen.add(prompt)
    assert len(seen) > 300
    assert question_at({"order": [0]}, 0)[2] == 1
    assert isinstance(Service(None, None).rng, random.SystemRandom)
