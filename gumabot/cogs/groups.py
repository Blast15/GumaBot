import discord
from discord import app_commands

from ..views.ui import buttons, send


class MarketGroup(app_commands.Group):
    def __init__(self, app, name="market"):
        super().__init__(name=name, description="Browse and trade card listings")
        self.app = app

    @app_commands.command(name="browse", description="Browse available listings")
    async def browse(self, i: discord.Interaction, page: int = 1):
        await i.response.defer(ephemeral=True)
        rows = await self.app.market.browse(page - 1)
        await send(
            i,
            "Marketplace",
            rows,
            buttons([(f"Buy {r['name']} · {r['price']}", f"buy:{r['id']}") for r in rows]),
        )

    @app_commands.command(name="list", description="List one of your available cards")
    async def list_card(self, i: discord.Interaction, code: str, price: int):
        await i.response.defer(ephemeral=True)
        await send(i, "Listing created", await self.app.market.list_card(i.user.id, code, price))

    @app_commands.command(name="buy", description="Buy an active listing atomically")
    async def buy(self, i: discord.Interaction, listing: str):
        await i.response.defer(ephemeral=True)
        await self.app.market.buy(i.user.id, listing)
        await send(i, "Marketplace", "Purchase completed.")

    @app_commands.command(name="remove", description="Remove your active listing")
    async def remove(self, i: discord.Interaction, listing: str):
        await i.response.defer(ephemeral=True)
        await self.app.market.remove(i.user.id, listing)
        await send(i, "Marketplace", "Listing removed.")


class AuctionGroup(app_commands.Group):
    def __init__(self, app):
        super().__init__(name="auction", description="Escrow-backed card auctions")
        self.app = app

    @app_commands.command(name="create", description="Create an auction for one available card")
    async def create(
        self,
        i: discord.Interaction,
        code: str,
        price: int,
        hours: int = 24,
        increment: int = 5,
        buyout: int | None = None,
    ):
        await i.response.defer(ephemeral=True)
        await send(
            i,
            "Auction created",
            await self.app.auctions.create(i.user.id, code, price, hours, increment, buyout),
        )

    @app_commands.command(name="bid", description="Reserve coins for an auction bid")
    async def bid(self, i: discord.Interaction, auction: str, amount: int):
        await i.response.defer(ephemeral=True)
        await self.app.auctions.bid(i.user.id, auction, amount)
        await send(i, "Auction", "Bid accepted and funds reserved.")

    @app_commands.command(name="info", description="Inspect an auction")
    async def info(self, i: discord.Interaction, auction: str):
        await i.response.defer(ephemeral=True)
        async with self.app.db.read() as tx:
            row = await tx.one(
                "SELECT a.id,a.seller,a.current_bid,a.bidder,a.start_price,a.increment,a.buyout,a.due_at,a.status,c.name,o.public_code FROM auctions a JOIN owned_cards o ON o.id=a.card_id JOIN card_catalog c ON c.id=o.catalog_card_id WHERE a.id=:id",
                id=auction,
            )
        await send(i, "Auction", row)

    @app_commands.command(name="cancel", description="Cancel your active auction if it has no bids")
    async def cancel(self, i: discord.Interaction, auction: str):
        await i.response.defer(ephemeral=True)
        await self.app.auctions.cancel(i.user.id, auction)
        await send(i, "Auction", "Cancelled.")


class WishlistGroup(app_commands.Group):
    def __init__(self, app):
        super().__init__(name="wishlist", description="Manage your private card wishlist")
        self.app = app

    @app_commands.command(name="add", description="Add a catalog card to your wishlist")
    async def add(self, i: discord.Interaction, card_id: str):
        await i.response.defer(ephemeral=True)
        await send(i, "Wishlist", await self.app.cards.wishlist(i.user.id, "add", card_id))

    @app_commands.command(name="remove", description="Remove a catalog card from your wishlist")
    async def remove(self, i: discord.Interaction, card_id: str):
        await i.response.defer(ephemeral=True)
        await send(i, "Wishlist", await self.app.cards.wishlist(i.user.id, "remove", card_id))

    @app_commands.command(name="list", description="Show your wishlist")
    async def list_cards(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        await send(i, "Wishlist", await self.app.cards.wishlist(i.user.id, "list"))


class AdminGroup(app_commands.Group):
    def __init__(self, bot):
        super().__init__(name="admin", description="Bot-owner maintenance")
        self.bot = bot

    @app_commands.command(
        name="sync_cards", description="Synchronize a card set into local cache (bot owner only)"
    )
    async def sync_cards(self, i: discord.Interaction, set_id: str):
        if not await self.bot.is_owner(i.user):
            from ..services.errors import DomainError

            raise DomainError("This command is restricted to the bot owner.")
        await i.response.defer(ephemeral=True)
        cards = await self.bot.app.provider.get_set_cards(set_id)
        await send(i, "Card sync", f"Cached {len(cards)} cards.")
