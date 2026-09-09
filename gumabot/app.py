import httpx

from .database.db import Database
from .providers.tcgdex import TCGdexProvider
from .rendering.images import Images
from .services.auctions import Auctions
from .services.cards import Cards
from .services.claims import Claims
from .services.economy import Economy
from .services.gameplay import Gameplay
from .services.grading import Grading
from .services.market import Market
from .services.progression import Progression
from .services.rules import validate_rules
from .services.trades import Trades
from .utils.clock import Clock


class Application:
    def __init__(self, settings, clock=None):
        self.settings = settings
        self.clock = clock or Clock()
        self.db = Database(settings.database)
        self.http = httpx.AsyncClient(
            timeout=httpx.Timeout(10, connect=5),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            follow_redirects=False,
        )
        self.provider = TCGdexProvider(
            self.http, self.db, self.clock, settings.api_base, settings.language
        )
        self.images = Images(self.http, settings.database.parent / "cache" / "images")
        self.cards = Cards(self.db, self.clock, self.provider)
        self.economy = Economy(self.db, self.clock, self.cards)
        self.market = Market(self.db, self.clock)
        self.auctions = Auctions(self.db, self.clock)
        self.trades = Trades(self.db, self.clock)
        self.grading = Grading(self.db, self.clock)
        self.claims = Claims(self.db, self.clock, self.cards)
        self.gameplay = Gameplay(self.db, self.clock, self.cards)
        self.progression = Progression(self.db, self.clock)

    async def initialize(self):
        validate_rules()
        await self.db.initialize()

    async def close(self):
        await self.images.close()
        await self.provider.close()
        await self.http.aclose()
        await self.db.close()
