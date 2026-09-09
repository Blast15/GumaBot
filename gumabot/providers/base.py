from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol


@dataclass(slots=True)
class CardDefinition:
    provider_id: str
    name: str
    set_id: str
    set_name: str
    local_id: str
    rarity: str | None
    category: str | None
    hp: int | None
    types: tuple[str, ...]
    image_url: str | None
    illustrator: str | None
    release_date: date | None
    raw_data: dict[str, Any]


class CardDataProvider(Protocol):
    async def get_card(self, card_id: str) -> CardDefinition: ...
    async def search_cards(self, query: str) -> list[CardDefinition]: ...
    async def list_sets(self) -> list[dict]: ...
    async def get_set(self, set_id: str) -> dict: ...
    async def get_set_cards(self, set_id: str) -> list[CardDefinition]: ...
    async def get_random_card(self, set_id: str) -> CardDefinition: ...
    async def get_cards_by_rarity(self, set_id: str, rarity: str) -> list[CardDefinition]: ...
    async def get_upcoming_sets(self) -> list[dict]: ...
