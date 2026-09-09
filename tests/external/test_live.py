import httpx
import pytest

from gumabot.providers.tcgdex import TCGdexProvider


@pytest.mark.external
async def test_live_tcgdex(app):
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5)) as client:
        provider = TCGdexProvider(client, app.db, app.clock)
        card = await provider.get_card("base1-1")
        assert card.provider_id == "base1-1" and card.name
