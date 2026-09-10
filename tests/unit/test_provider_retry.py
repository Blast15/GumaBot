from datetime import UTC, datetime
from email.utils import format_datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from gumabot.services.errors import ProviderUnavailable


@pytest.mark.parametrize(
    "header", ["2", "bad", "-4", "nan", "inf", "Wed, 21 Oct 2015 07:28:00 GMT"]
)
async def test_retry_after_parsing(app, header):
    response = httpx.Response(429, headers={"Retry-After": header})
    delay = app.provider.retry_delay(response, 0)
    assert delay >= (2 if header == "2" else 0.5)
    assert delay < (2.25 if header == "2" else 0.75)
    header = format_datetime(datetime.fromtimestamp(app.clock.timestamp() + 10, UTC))
    assert (
        10
        <= app.provider.retry_delay(httpx.Response(429, headers={"Retry-After": header}), 0)
        < 10.25
    )


async def test_429_sleeps_then_succeeds(app, monkeypatch):
    responses = [httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(200, json=[])]
    app.http._transport = httpx.MockTransport(lambda request: responses.pop(0))
    sleep = AsyncMock()
    monkeypatch.setattr("gumabot.providers.tcgdex.asyncio.sleep", sleep)
    assert await app.provider.request("/sets") == []
    assert sleep.call_count == 1 and sleep.call_args.args[0] >= 2


async def test_retry_budget_blocks_new_calls_and_uses_stale_cache(app):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})

    app.http._transport = httpx.MockTransport(handler)
    with pytest.raises(ProviderUnavailable):
        await app.provider.request("/sets")
    with pytest.raises(ProviderUnavailable):
        await app.provider.request("/sets/other")
    assert len(calls) == 1
    async with app.db.transaction() as tx:
        await tx.execute(
            "INSERT INTO provider_cache VALUES (:key,'[]',0)", key=app.provider.base + "/sets"
        )
    assert await app.provider.request("/sets") == []


async def test_circuit_breaker_after_three_failures(app, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    app.http._transport = httpx.MockTransport(handler)
    monkeypatch.setattr("gumabot.providers.tcgdex.asyncio.sleep", AsyncMock())
    for _ in range(4):
        with pytest.raises(ProviderUnavailable):
            await app.provider.request("/sets")
    assert len(calls) == 9
