import asyncio
import json
import logging
import random
import re
from dataclasses import asdict
from datetime import date

import httpx

from ..services.errors import DomainError, ProviderUnavailable
from ..services.rules import normalize, rarity
from .base import CardDataProvider, CardDefinition

log = logging.getLogger(__name__)


class TCGdexProvider(CardDataProvider):
    def __init__(
        self, client, db, clock, base="https://api.tcgdex.net/v2/en", language="en", rng=None
    ):
        self.client, self.db, self.clock = client, db, clock
        self.base = base.rstrip("/").rsplit("/", 1)[0] + "/" + language
        self.semaphore = asyncio.Semaphore(5)
        self.inflight = {}
        self.rng = rng or random.Random()

    @staticmethod
    def identifier(value):
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", value):
            raise DomainError("Invalid card or set ID.")
        return value

    @staticmethod
    def valid_payload(path, data):
        if path == "/sets" or path.startswith("/cards?"):
            return isinstance(data, list) and all(
                isinstance(c, dict) and isinstance(c.get("id"), str) for c in data
            )
        if not isinstance(data, dict) or not isinstance(data.get("id"), str):
            return False
        if path.startswith("/sets/"):
            return isinstance(data.get("cards"), list) and all(
                isinstance(c, dict) and isinstance(c.get("id"), str) for c in data["cards"]
            )
        card_set = data.get("set")
        return (
            isinstance(data.get("name"), str)
            and isinstance(card_set, dict)
            and isinstance(card_set.get("id"), str)
            and isinstance(card_set.get("name"), str)
        )

    async def _fetch(self, path, ttl):
        key = self.base + path
        async with self.db.read() as tx:
            row = await tx.one("SELECT * FROM provider_cache WHERE key=:key", key=key)
        cached = None
        if row:
            try:
                cached = json.loads(row["payload"])
                if not self.valid_payload(path, cached):
                    cached = None
            except (ValueError, TypeError):
                pass
            if cached is not None and row["expires_at"] > self.clock.timestamp():
                return cached
        try:
            async with asyncio.timeout(40):
                for attempt in range(3):
                    try:
                        async with self.semaphore:
                            response = await self.client.get(key)
                            if response.status_code == 404 and not self.base.endswith("/en"):
                                response = await self.client.get(
                                    self.base.rsplit("/", 1)[0] + "/en" + path
                                )
                        if response.status_code == 429 or response.status_code in (
                            500,
                            502,
                            503,
                            504,
                        ):
                            raise httpx.ReadTimeout("Temporary upstream error")
                        response.raise_for_status()
                        data = response.json()
                        if not self.valid_payload(path, data):
                            raise ValueError("Invalid JSON structure")
                        async with self.db.transaction() as tx:
                            await tx.execute(
                                "INSERT INTO provider_cache VALUES (:key,:payload,:expires) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,expires_at=excluded.expires_at",
                                key=key,
                                payload=json.dumps(data),
                                expires=self.clock.timestamp() + ttl,
                            )
                        return data
                    except (httpx.TimeoutException, httpx.NetworkError):
                        if attempt == 2:
                            raise
                        await asyncio.sleep(0.2 * 2**attempt + self.rng.random() * 0.1)
        except (httpx.HTTPError, ValueError, TimeoutError):
            log.warning("Card provider unavailable for resource %s", path)
            if cached is not None:
                return cached
            raise ProviderUnavailable() from None

    async def request(self, path, ttl=604800):
        if path not in self.inflight:
            task = asyncio.create_task(self._fetch(path, ttl))
            self.inflight[path] = task
            task.add_done_callback(lambda done: self.inflight.pop(path, None))
        return await asyncio.shield(self.inflight[path])

    async def close(self):
        tasks = list(self.inflight.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def list_sets(self):
        data = await self.request("/sets", 86400)
        if not isinstance(data, list):
            raise ProviderUnavailable()
        return [
            {"id": x["id"], "name": x.get("name", x["id"])}
            for x in data
            if isinstance(x, dict) and "id" in x
        ]

    async def get_set(self, set_id):
        data = await self.request("/sets/" + self.identifier(set_id), 86400)
        if (
            not isinstance(data, dict)
            or "id" not in data
            or not isinstance(data.get("cards", []), list)
        ):
            raise ProviderUnavailable()
        result = {
            "id": data["id"],
            "name": data.get("name", set_id),
            "total": len(data.get("cards", [])),
            "release_date": data.get("releaseDate"),
            "cards": [c["id"] for c in data.get("cards", []) if "id" in c],
        }
        async with self.db.transaction() as tx:
            await tx.execute(
                "INSERT INTO card_sets VALUES (:id,:name,:total,:release_date,:now) ON CONFLICT(id) DO UPDATE SET name=excluded.name,total=excluded.total,release_date=excluded.release_date,synced_at=excluded.synced_at",
                **{k: v for k, v in result.items() if k != "cards"},
                now=self.clock.timestamp(),
            )
        return result

    async def get_card(self, card_id):
        data = await self.request("/cards/" + self.identifier(card_id))
        try:
            s = data["set"]
            release = s.get("releaseDate")
            image = data.get("image")
            card = CardDefinition(
                data["id"],
                data["name"],
                s["id"],
                s["name"],
                str(data.get("localId", "")),
                data.get("rarity"),
                data.get("category"),
                int(data["hp"]) if data.get("hp") else None,
                tuple(data.get("types", [])),
                image + "/high.webp" if image else None,
                data.get("illustrator"),
                date.fromisoformat(release) if release else None,
                data,
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ProviderUnavailable() from None
        async with self.db.transaction() as tx:
            await tx.execute(
                "INSERT INTO card_sets VALUES (:id,:name,:total,:release,:now) ON CONFLICT(id) DO NOTHING",
                id=card.set_id,
                name=card.set_name,
                total=s.get("cardCount", {}).get("total", 0),
                release=release,
                now=self.clock.timestamp(),
            )
            await tx.execute(
                "INSERT INTO card_catalog VALUES (:id,:name,:search,:set,:rarity,:metadata) ON CONFLICT(id) DO UPDATE SET name=excluded.name,search_name=excluded.search_name,rarity=excluded.rarity,metadata=excluded.metadata",
                id=card.provider_id,
                name=card.name,
                search=normalize(card.name),
                set=card.set_id,
                rarity=int(rarity(card.rarity)),
                metadata=json.dumps(asdict(card), default=str),
            )
        return card

    async def get_set_cards(self, set_id):
        metadata = await self.get_set(set_id)
        # Chunk task creation as well as HTTP concurrency for bounded memory.
        results = []
        for offset in range(0, len(metadata["cards"]), 5):
            results.extend(
                await asyncio.gather(
                    *(self.get_card(c) for c in metadata["cards"][offset : offset + 5])
                )
            )
        return results

    async def search_cards(self, query):
        from urllib.parse import quote

        data = await self.request("/cards?name=" + quote(query[:100]), 86400)
        if not isinstance(data, list):
            raise ProviderUnavailable()
        return await asyncio.gather(
            *(self.get_card(c["id"]) for c in data[:20] if isinstance(c, dict) and "id" in c)
        )

    async def get_random_card(self, set_id):
        cards = await self.get_set_cards(set_id)
        if not cards:
            raise ProviderUnavailable()
        return self.rng.choice(cards)

    async def get_cards_by_rarity(self, set_id, value):
        return [c for c in await self.get_set_cards(set_id) if rarity(c.rarity) == rarity(value)]

    async def get_upcoming_sets(self):
        # Only report verified dates from metadata already synchronized locally.
        async with self.db.read() as tx:
            return await tx.all(
                "SELECT id,name,release_date FROM card_sets WHERE release_date>=:today ORDER BY release_date LIMIT 20",
                today=self.clock.now().date().isoformat(),
            )
