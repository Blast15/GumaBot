import asyncio

import httpx
import pytest

from gumabot.providers.tcgdex import TCGdexProvider
from gumabot.services.errors import DomainError, ProviderUnavailable

CARD = {
    "id": "base1-1",
    "name": "Alakazam",
    "localId": "1",
    "set": {"id": "base1", "name": "Base", "cardCount": {"total": 1}},
    "rarity": "Rare Holo",
    "hp": 80,
    "types": ["Psychic"],
    "image": "https://assets.tcgdex.net/en/base/base1/1",
}
SET = {"id": "base1", "name": "Base", "releaseDate": "1999-01-09", "cards": [{"id": "base1-1"}]}


async def provider(app, handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TCGdexProvider(client, app.db, app.clock), client


async def test_card_normalization_cache_singleflight(app):
    calls = []

    async def handler(request):
        calls.append(request.url.path)
        await asyncio.sleep(0.01)
        return httpx.Response(200, json=CARD)

    p, client = await provider(app, handler)
    async with client:
        cards = await asyncio.gather(*(p.get_card("base1-1") for _ in range(20)))
        assert len(calls) == 1
        assert cards[0].name == "Alakazam" and cards[0].hp == 80
        assert (await p.get_card("base1-1")).image_url.endswith("/high.webp")
        assert len(calls) == 1
        app.clock.advance(604801)
        await p.get_card("base1-1")
        assert len(calls) == 2


@pytest.mark.parametrize("status", [404, 429, 500, 503])
async def test_provider_http_errors_and_stale(app, status):
    mode = [200]
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(mode[0], json=CARD)

    p, client = await provider(app, handler)
    async with client:
        await p.get_card("base1-1")
        app.clock.advance(604801)
        mode[0] = status
        assert (await p.get_card("base1-1")).name == "Alakazam"
        with pytest.raises(ProviderUnavailable):
            await p.get_card("base1-2")
        assert len(calls) <= 7


@pytest.mark.parametrize("mode", ["timeout", "json", "shape", "missing", "empty"])
async def test_provider_invalid(app, mode):
    def handler(request):
        if mode == "timeout":
            raise httpx.ReadTimeout("test")
        if mode == "json":
            return httpx.Response(200, content=b"{")
        return httpx.Response(200, json={"shape": 12, "missing": {}, "empty": []}[mode])

    p, client = await provider(app, handler)
    async with client:
        with pytest.raises(ProviderUnavailable):
            await p.get_card("base1-1")


async def test_missing_optional_fields(app):
    p, client = await provider(
        app,
        lambda r: httpx.Response(
            200, json={k: v for k, v in CARD.items() if k not in ("rarity", "image")}
        ),
    )
    async with client:
        card = await p.get_card("base1-1")
        assert card.rarity is None and card.image_url is None


async def test_sets_search_empty_upcoming_corrupt_cache(app):
    def handler(request):
        path = request.url.path
        if path.endswith("/sets"):
            value = [{"id": "base1", "name": "Base"}]
        elif "/sets/" in path:
            value = SET if path.endswith("base1") else {"id": "empty", "name": "Empty", "cards": []}
        elif path.endswith("/cards"):
            value = [{"id": "base1-1"}]
        else:
            value = CARD
        return httpx.Response(200, json=value)

    p, client = await provider(app, handler)
    async with client:
        assert len(await p.list_sets()) == 1
        assert (await p.get_set("base1"))["total"] == 1
        assert len(await p.get_set_cards("base1")) == 1
        assert len(await p.search_cards("Alakazam")) == 1
        assert (await p.get_random_card("base1")).provider_id == "base1-1"
        assert len(await p.get_cards_by_rarity("base1", "Holo")) == 1
        assert await p.get_set_cards("empty") == []
        with pytest.raises(ProviderUnavailable):
            await p.get_random_card("empty")
        assert await p.get_upcoming_sets() == []
        async with app.db.transaction() as tx:
            await tx.execute(
                "UPDATE provider_cache SET payload='broken' WHERE key LIKE '%/cards/base1-1'"
            )
        assert (await p.get_card("base1-1")).name == "Alakazam"
        with pytest.raises(DomainError):
            await p.get_card("../../secrets")


async def test_language_fallback(app):
    paths = []

    def handler(r):
        paths.append(r.url.path)
        return httpx.Response(404) if "/zz/" in r.url.path else httpx.Response(200, json=CARD)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    p = TCGdexProvider(client, app.db, app.clock, language="zz")
    async with client:
        assert (await p.get_card("base1-1")).name == "Alakazam"
        assert paths == ["/v2/zz/cards/base1-1", "/v2/en/cards/base1-1"]
