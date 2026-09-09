import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from conftest import users

from gumabot.jobs.manager import Jobs
from gumabot.jobs.webhook import Webhook


class Request:
    def __init__(self, payload, headers):
        self.payload = payload
        self.headers = headers

    async def read(self):
        return self.payload


async def test_signed_webhook_queue_replay_and_worker(app):
    await users(app, 1)
    app.settings.webhook_version = "v1"
    webhook = Webhook(app)
    body = json.dumps(
        {
            "type": "vote.create",
            "data": {
                "id": "event-one",
                "project": {"platform_id": "123", "platform": "discord", "type": "bot"},
                "user": {"platform_id": "1"},
            },
        }
    ).encode()
    stamp = str(app.clock.timestamp())
    signature = hmac.new(
        app.settings.webhook_secret.encode(), stamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    request = Request(body, {"x-topgg-signature": f"t={stamp},v1={signature}"})
    assert (await webhook.vote(request)).status == 200
    assert (await webhook.vote(request)).status == 200
    assert (await webhook.health(request)).status == 200
    jobs = Jobs(SimpleNamespace(app=app))
    await jobs.process_votes()
    await jobs.process_votes()
    async with app.db.read() as tx:
        assert (await tx.one("SELECT COUNT(*) AS n FROM vote_events"))["n"] == 1
        assert (await tx.one("SELECT status FROM vote_inbox"))["status"] == "completed"
    with pytest.raises(web.HTTPUnauthorized):
        await webhook.vote(Request(body, {}))
    with pytest.raises(web.HTTPUnauthorized):
        await webhook.vote(Request(body, {"x-topgg-signature": f"t={stamp},v1=invalid"}))
    app.clock.advance(301)
    with pytest.raises(web.HTTPUnauthorized):
        await webhook.vote(request)


async def test_legacy_webhook_validation(app):
    app.settings.webhook_version = "v0"
    webhook = Webhook(app)
    headers = {"Authorization": app.settings.webhook_secret}
    with pytest.raises(web.HTTPUnauthorized):
        await webhook.vote(Request(b"{}", {}))
    for payload in (
        b"{",
        b"[]",
        json.dumps({"type": "upvote", "bot": "wrong", "user": "1"}).encode(),
    ):
        with pytest.raises(web.HTTPBadRequest):
            await webhook.vote(Request(payload, headers))
    assert (await webhook.vote(Request(b'{"type":"test"}', headers))).status == 200
    assert (
        await webhook.vote(Request(b'{"type":"upvote","bot":"123","user":"1"}', headers))
    ).status == 200
    jobs = Jobs(SimpleNamespace(app=app))
    await jobs.process_votes()
    async with app.db.read() as tx:
        assert (await tx.one("SELECT status FROM vote_inbox"))["status"] == "ignored"


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


async def test_http_server_same_process_lifecycle(app):
    app.settings.webhook_version = "v1"
    app.settings.webhook_host = "127.0.0.1"
    app.settings.webhook_port = 0
    webhook = Webhook(app)
    await webhook.start()
    assert webhook.runner.sites
    await webhook.close()
