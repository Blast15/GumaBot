from types import SimpleNamespace
from unittest.mock import AsyncMock

from conftest import users

from gumabot.jobs.manager import Jobs


async def test_jobs_reminder_claim_and_cancellation(app):
    await users(app, 1)
    await app.economy.daily(1)
    await app.progression.reminder(1, "daily", True)
    await app.progression.reminder(1, "energy", True)
    user = SimpleNamespace(send=AsyncMock())
    bot = SimpleNamespace(
        app=app,
        get_user=lambda uid: user,
        fetch_user=AsyncMock(return_value=user),
        wait_until_ready=AsyncMock(),
    )
    jobs = Jobs(bot)
    await jobs.reminders()
    assert user.send.call_count == 1
    app.clock.advance(86401)
    await jobs.tick()
    await jobs.tick()
    assert user.send.call_count == 2
    jobs.start()
    await jobs.close()
