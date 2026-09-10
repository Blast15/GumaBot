from unittest.mock import AsyncMock

import pytest
from conftest import users

from gumabot.cogs.gameplay import GameplayCommands
from gumabot.services.errors import DomainError


def test_pickcard_description_allows_small_pools():
    assert GameplayCommands.pickcard.description == (
        "Choose one of up to three cards every thirty minutes"
    )


@pytest.mark.parametrize("size", [1, 2, 3])
async def test_pickcard_invalid_choice_reports_actual_count(app, size):
    await users(app, 1)
    async with app.db.read() as tx:
        pool = await tx.all("SELECT * FROM card_catalog ORDER BY id LIMIT :n", n=size)
    app.cards.ensure_set = AsyncMock(return_value=pool)

    key = await app.gameplay.new_session(1, "pickcard", "test")

    with pytest.raises(
        DomainError,
        match=rf"^Choose one of the {size} available cards\.$",
    ):
        await app.gameplay.session_action(1, key, str(size))
