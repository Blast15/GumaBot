import json

import discord
from discord import app_commands
from discord.ext import commands

from ..services.errors import DomainError
from ..services.rules import Rarity
from ..views.ui import GUIDE, ReportModal, buttons, send, show_duel, show_session


class GameCommands(commands.Cog):
    def __init__(self, bot):
        self.bot, self.app = bot, bot.app

    async def defer(self, i):
        await i.response.defer(ephemeral=True)

    @app_commands.command(
        name="start", description="Create your trainer and claim your starter pack once"
    )
    async def start(self, i: discord.Interaction):
        await self.defer(i)
        await send(
            i,
            "Welcome to GumaBot",
            await self.app.cards.start(i.user.id, self.app.settings.featured_set),
        )

    @app_commands.command(name="openpack", description="Open five cards using one energy")
    @app_commands.rename(set_id="set")
    async def openpack(self, i: discord.Interaction, set_id: str = ""):
        await self.defer(i)
        result = await self.app.cards.open_pack(
            i.user.id, set_id or self.app.settings.featured_set, str(i.id)
        )
        await send(
            i,
            "God Pack!" if result["god"] else "Your pack",
            result,
            buttons(
                [
                    ("Reveal cards", f"reveal:{i.user.id}:{result['pack']}"),
                    ("Inventory", f"inventory:{i.user.id}:0"),
                    ("Play", f"dashboard:{i.user.id}"),
                ]
            ),
        )

    @app_commands.command(name="play", description="Open your trainer dashboard")
    async def play(self, i: discord.Interaction):
        await self.defer(i)
        await self.dashboard(i)

    async def dashboard(self, i):
        user = await self.app.economy.balance(i.user.id)
        await send(
            i,
            "GumaBot",
            {k: user[k] for k in ("coins", "aura", "xp", "level", "energy", "energy_updated_at")}
            | {"featured_set": self.app.settings.featured_set, "daily": "/daily", "vote": "/vote"},
            buttons(
                [
                    (x.title(), f"dash:{i.user.id}:{x}")
                    for x in (
                        "packs",
                        "inventory",
                        "collection",
                        "market",
                        "battle",
                        "quests",
                        "guide",
                    )
                ]
            ),
        )

    @app_commands.command(name="guide", description="Seven-page GumaBot tutorial")
    async def guide(self, i: discord.Interaction):
        await self.guide_page(i, 0)

    async def guide_page(self, i, page):
        page = max(0, min(6, page))
        await send(
            i,
            f"Guide {page + 1}/7",
            GUIDE[page],
            buttons(
                [
                    ("Previous", f"guide:{i.user.id}:{max(0, page - 1)}"),
                    ("Next", f"guide:{i.user.id}:{min(6, page + 1)}"),
                    ("Close", f"close:{i.user.id}"),
                ]
            ),
        )

    @app_commands.command(
        name="help", description="List the commands actually registered in this bot"
    )
    async def help(self, i: discord.Interaction):
        names = sorted(
            "/" + c.qualified_name
            for c in self.bot.tree.walk_commands()
            if not isinstance(c, app_commands.Group)
        )
        await send(i, "GumaBot commands", "\n".join(names))

    @app_commands.command(
        name="inventory", description="Filter, sort and page through your card instances"
    )
    @app_commands.rename(set_id="set", condition_name="condition")
    async def inventory(
        self,
        i: discord.Interaction,
        page: app_commands.Range[int, 1, 100000] = 1,
        name: str = "",
        set_id: str = "",
        rarity: Rarity | None = None,
        condition_name: str = "",
        graded: bool | None = None,
        duplicate: bool = False,
        sort: str = "newest",
    ):
        await self.defer(i)
        rows = await self.app.cards.inventory(
            i.user.id, page - 1, name, set_id, rarity, condition_name, graded, duplicate, sort
        )
        await self.show_inventory(
            i,
            rows,
            page - 1,
            controls=not any(
                (
                    name,
                    set_id,
                    condition_name,
                    rarity is not None,
                    graded is not None,
                    duplicate,
                    sort != "newest",
                )
            ),
        )

    async def show_inventory(self, i, rows, page, controls=True):
        output = [
            {
                "code": r["public_code"],
                "name": r["name"],
                "rarity": Rarity(r["rarity"]).name,
                "condition": r["condition_name"],
                "grade": r["grade"],
                "locked": r["locked_reason"],
            }
            for r in rows
        ]
        await send(
            i,
            f"Inventory · page {page + 1}",
            output,
            buttons(
                [
                    ("Previous", f"inventory:{i.user.id}:{max(0, page - 1)}"),
                    ("Next", f"inventory:{i.user.id}:{page + 1}"),
                ]
            )
            if controls
            else None,
        )

    @app_commands.command(name="find", description="Find cards by name in your inventory")
    async def find(self, i: discord.Interaction, name: str):
        await self.defer(i)
        await self.show_inventory(i, await self.app.cards.find(i.user.id, name), 0, False)

    @find.autocomplete("name")
    async def find_autocomplete(self, i, current):
        rows = await self.app.cards.inventory(i.user.id, name=current)
        return [
            app_commands.Choice(name=n[:100], value=n[:100])
            for n in sorted({r["name"] for r in rows})[:25]
        ]

    @app_commands.command(
        name="search", description="Inspect a card instance using its public code"
    )
    async def search(self, i: discord.Interaction, code: str):
        await self.defer(i)
        row = await self.app.cards.search(i.user.id, code)
        row.pop("metadata", None)
        row.pop("id", None)
        row["rarity"] = Rarity(row["rarity"]).name
        await send(i, "Card", row)

    @app_commands.command(name="daily", description="Claim your rolling 24-hour daily reward")
    async def daily(self, i: discord.Interaction):
        await self.defer(i)
        await send(i, "Daily", f"Received {await self.app.economy.daily(i.user.id)} coins.")

    @app_commands.command(
        name="give", description="Transfer coins or an available card to another player"
    )
    async def give(
        self, i: discord.Interaction, user: discord.User, amount: int = 1, code: str = ""
    ):
        await self.defer(i)
        if user.bot:
            raise DomainError("Choose a human player.")
        await self.app.economy.give(i.user.id, user.id, amount, code, str(i.id))
        await send(i, "Gift", "Transfer completed.")

    @app_commands.command(name="buyitem", description="Purchase items using virtual coins")
    async def buyitem(self, i: discord.Interaction, item: str, quantity: int = 1):
        await self.defer(i)
        await self.app.economy.buy_item(i.user.id, item, quantity, str(i.id))
        await send(i, "Item shop", "Purchase completed.")

    @app_commands.command(name="buypack", description="Buy one energy for 40 coins")
    async def buypack(self, i: discord.Interaction):
        await self.defer(i)
        await self.app.economy.buy_pack(i.user.id, str(i.id))
        await send(i, "Packs", "Added one energy. Use /openpack.")

    @app_commands.command(
        name="resetpack", description="Compatibility alias: buy one energy for 40 coins"
    )
    async def resetpack(self, i: discord.Interaction):
        await self.buypack.callback(self, i)

    @app_commands.command(name="mysterybox", description="Open a mystery box from your items")
    async def mysterybox(self, i: discord.Interaction):
        await self.defer(i)
        await send(
            i,
            "Mystery box",
            await self.app.economy.mystery_box(
                i.user.id, self.app.settings.featured_set, str(i.id)
            ),
        )

    @app_commands.command(name="grade", description="Submit a raw card for timed grading")
    async def grade(
        self, i: discord.Interaction, code: str, lane: str = "economy", coupon: bool = False
    ):
        await self.defer(i)
        await send(i, "Grading", await self.app.grading.submit(i.user.id, code, lane, coupon))

    @app_commands.command(name="checkgrade", description="Check grading ETA or your certificate")
    async def checkgrade(self, i: discord.Interaction, code: str):
        await self.defer(i)
        certificate = await self.app.grading.check(i.user.id, code)
        file = None
        if certificate and certificate["certificate"]:
            card = await self.app.cards.search(i.user.id, code)
            card.update(certificate)
            card["image_url"] = json.loads(card["metadata"])["image_url"]
            try:
                file = discord.File(
                    await self.app.images.render([card]), filename="gumabot-certificate.png"
                )
            except (OSError, ValueError):
                pass
        await send(i, "Grading certificate", certificate, file=file)

    @app_commands.command(
        name="fuse", description="Fuse three raw duplicate instances into an improved card"
    )
    async def fuse(self, i: discord.Interaction, code1: str, code2: str, code3: str):
        await self.defer(i)
        await send(
            i,
            "Fusion",
            await self.app.cards.fuse(i.user.id, [code1.upper(), code2.upper(), code3.upper()]),
        )

    @app_commands.command(
        name="swapcodes", description="Swap two of your available card codes atomically"
    )
    async def swapcodes(self, i: discord.Interaction, first: str, second: str):
        await self.defer(i)
        await self.app.cards.swap_codes(i.user.id, first.upper(), second.upper())
        await send(i, "Card codes", "Codes swapped.")

    @app_commands.command(
        name="tint", description="Apply a tint token to a card without changing the original image"
    )
    async def tint(self, i: discord.Interaction, code: str, color: str):
        await self.defer(i)
        await self.app.cards.tint(i.user.id, code, color)
        await send(i, "Tint", "Tint applied. View /showcase.")

    @app_commands.command(name="showcase", description="Render your nine highest-graded cards")
    async def showcase(self, i: discord.Interaction):
        await self.defer(i)
        cards = (await self.app.cards.inventory(i.user.id, sort="grade"))[:9]
        for card in cards:
            card["image_url"] = json.loads(card["metadata"])["image_url"]
        if not cards:
            raise DomainError("Your inventory is empty.")
        try:
            image = await self.app.images.render(cards)
        except (OSError, ValueError):
            await self.show_inventory(i, cards, 0, False)
            return
        await send(
            i,
            "GumaBot showcase",
            "Your collection",
            file=discord.File(image, filename="showcase.png"),
        )

    @app_commands.command(
        name="peek", description="Offer a spare duplicate for another player to claim"
    )
    async def peek(self, i: discord.Interaction, code: str):
        await self.defer(i)
        key = await self.app.claims.peek(i.user.id, code)
        await send(
            i,
            "Pack Peek",
            "One other player can claim this duplicate within ten minutes.",
            buttons([("Claim", f"peek:{key}")]),
            ephemeral=False,
        )

    @app_commands.command(
        name="sell", description="Preview a bulk sale of up to 25 unprotected raw cards"
    )
    async def sell(self, i: discord.Interaction):
        await self.defer(i)
        cards = await self.app.market.sell_preview(i.user.id)
        if not cards:
            raise DomainError("No eligible cards to sell.")
        key = self.app.cards.identifier()
        async with self.app.db.transaction() as tx:
            await self.app.cards.save_receipt(
                tx,
                i.user.id,
                key,
                "sell_preview",
                {
                    "codes": [c["public_code"] for c in cards],
                    "due": self.app.clock.timestamp() + 120,
                },
            )
        await send(
            i,
            "Confirm bulk sale",
            cards,
            buttons([("Confirm sale", f"sell:{key}"), ("Cancel", f"close:{i.user.id}")]),
        )

    @app_commands.command(
        name="cardtrend", description="View actual market sale statistics for 7 or 30 days"
    )
    async def cardtrend(self, i: discord.Interaction, card_id: str, days: int = 30):
        await self.defer(i)
        await send(i, "Price history", await self.app.market.trend(card_id, days))

    @app_commands.command(
        name="trade", description="Invite, accept, inspect or update an escrow-backed trade"
    )
    async def trade(
        self,
        i: discord.Interaction,
        user: discord.User | None = None,
        action: str = "info",
        trade_id: str = "",
        kind: str = "card",
        reference: str = "",
        amount: int = 1,
    ):
        await self.defer(i)
        service = self.app.trades
        if user:
            if user.bot:
                raise DomainError("Choose a human player.")
            trade_id = await service.invite(i.user.id, user.id)
        elif action == "accept":
            await service.accept(i.user.id, trade_id)
        elif action == "add":
            await service.add(i.user.id, trade_id, kind, reference, amount)
        elif action == "confirm":
            await service.confirm(i.user.id, trade_id)
        elif action == "cancel":
            await service.cancel(i.user.id, trade_id)
        elif action != "info":
            raise DomainError("Actions: info, accept, add, confirm, cancel.")
        await self.trade_info(i, trade_id)

    async def trade_info(self, i, key):
        async with self.app.db.read() as tx:
            row = await tx.one(
                "SELECT * FROM trades WHERE id=:id AND (proposer=:u OR recipient=:u)",
                id=key,
                u=i.user.id,
            )
            items = (
                await tx.all(
                    "SELECT t.user_id,t.kind,CASE WHEN t.kind='card' THEN o.public_code ELSE t.reference END AS reference,t.amount FROM trade_items t LEFT JOIN owned_cards o ON t.kind='card' AND o.id=CAST(t.reference AS INTEGER) WHERE t.trade_id=:id",
                    id=key,
                )
                if row
                else []
            )
        if not row:
            raise DomainError("Trade not found.")
        await send(
            i,
            "Trade " + key,
            {"trade": row, "offers": items},
            buttons([(a.title(), f"trade:{key}:{a}") for a in ("accept", "confirm", "cancel")]),
            ephemeral=False,
        )

    @app_commands.command(
        name="deck",
        description="Set exactly five public codes separated by spaces, or view your deck",
    )
    async def deck(self, i: discord.Interaction, codes: str = ""):
        await self.defer(i)
        await send(
            i,
            "Deck",
            await self.app.gameplay.deck(i.user.id, codes.upper().split() if codes else None),
        )

    @app_commands.command(name="duel", description="Challenge a player or resume a persisted duel")
    async def duel(
        self, i: discord.Interaction, user: discord.User | None = None, duel_id: str = ""
    ):
        await self.defer(i)
        if user:
            if user.bot:
                raise DomainError("Choose a human player.")
            duel_id = await self.app.gameplay.invite_duel(i.user.id, user.id)
        await show_duel(i, self.app, duel_id)

    @app_commands.command(name="gym", description="Challenge one of eight original gym leaders")
    async def gym(self, i: discord.Interaction, leader: app_commands.Range[int, 1, 8] = 1):
        await self.defer(i)
        await send(i, "Gym", await self.app.gameplay.gym(i.user.id, leader))

    @app_commands.command(
        name="blackjack", description="Play blackjack with virtual coins only; maximum wager 500"
    )
    async def blackjack(self, i: discord.Interaction, wager: int = 10, session: str = ""):
        await self.defer(i)
        key = session or await self.app.gameplay.new_session(i.user.id, "blackjack", wager=wager)
        await show_session(i, self.app, key)

    @app_commands.command(
        name="quiz", description="Answer up to ten questions in a persisted session"
    )
    async def quiz(self, i: discord.Interaction, session: str = ""):
        await self.defer(i)
        key = session or await self.app.gameplay.new_session(i.user.id, "quiz")
        await show_session(i, self.app, key)

    @app_commands.command(
        name="pickcard", description="Choose one of three cards every thirty minutes"
    )
    async def pickcard(self, i: discord.Interaction, session: str = ""):
        await self.defer(i)
        key = session or await self.app.gameplay.new_session(
            i.user.id, "pickcard", self.app.settings.featured_set
        )
        await show_session(i, self.app, key)

    @app_commands.command(
        name="namepokemon", description="Identify a Pokémon from its provider image"
    )
    async def namepokemon(self, i: discord.Interaction, session: str = ""):
        await self.defer(i)
        key = session or await self.app.gameplay.new_session(
            i.user.id, "namepokemon", self.app.settings.featured_set
        )
        await show_session(i, self.app, key)

    @app_commands.command(name="journey", description="Explore encounters, rest or use a potion")
    async def journey(self, i: discord.Interaction, action: str = "explore"):
        await self.defer(i)
        await send(
            i,
            "Journey",
            await self.app.gameplay.journey(i.user.id, action),
            buttons(
                [(a.title(), f"journey:{i.user.id}:{a}") for a in ("explore", "rest", "potion")]
            ),
        )

    @app_commands.command(name="reminder", description="Opt into or out of a personal reminder")
    async def reminder(self, i: discord.Interaction, kind: str, enabled: bool):
        await self.defer(i)
        await self.app.progression.reminder(i.user.id, kind, enabled)
        await send(i, "Reminders", "Preference saved.")

    @app_commands.command(name="report", description="Send bug feedback into the local database")
    async def report(self, i: discord.Interaction):
        await i.response.send_modal(ReportModal(self.app))

    @app_commands.command(
        name="avatarchoice", description="Choose your original GumaBot trainer avatar"
    )
    @app_commands.choices(
        avatar=[
            app_commands.Choice(name=x, value=x) for x in ("Scout", "Scholar", "Ranger", "Artisan")
        ]
    )
    async def avatarchoice(self, i: discord.Interaction, avatar: str):
        if avatar not in ("Scout", "Scholar", "Ranger", "Artisan"):
            raise DomainError("Invalid avatar.")
        await self.defer(i)
        async with self.app.db.transaction() as tx:
            await self.app.cards.user(tx, i.user.id)
            await tx.execute(
                "UPDATE users SET trainer_avatar=:a WHERE discord_user_id=:u", a=avatar, u=i.user.id
            )
        await send(i, "Trainer", avatar)

    @app_commands.command(name="setchannel", description="Configure server drops in a channel")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setchannel(
        self, i: discord.Interaction, channel: discord.TextChannel, enabled: bool = True
    ):
        if channel.guild.id != i.guild_id:
            raise DomainError("Choose a channel in this server.")
        await self.defer(i)
        async with self.app.db.transaction() as tx:
            await tx.execute(
                "INSERT INTO guilds(id,drop_channel,drop_enabled) VALUES (:g,:c,:e) ON CONFLICT(id) DO UPDATE SET drop_channel=:c,drop_enabled=:e",
                g=i.guild_id,
                c=channel.id,
                e=int(enabled),
            )
        await send(i, "Server drops", "Configuration saved.")

    @app_commands.command(
        name="leaderboard", description="Rank trainers by economy, collection or gameplay"
    )
    async def leaderboard(self, i: discord.Interaction, metric: str = "coins", page: int = 1):
        await self.defer(i)
        await send(
            i,
            "Leaderboard · " + metric,
            await self.app.progression.leaderboard(metric, page - 1),
            buttons(
                [
                    (x.title(), f"rank:{i.user.id}:{x}:0")
                    for x in (
                        "coins",
                        "aura",
                        "xp",
                        "collection",
                        "grades",
                        "duels",
                        "achievements",
                    )
                ]
            ),
        )

    @app_commands.command(
        name="vote", description="Get the Top.gg vote link; rewards require a verified webhook"
    )
    async def vote(self, i: discord.Interaction):
        bot_id = self.app.settings.topgg_bot_id
        await send(
            i,
            "Vote",
            f"https://top.gg/bot/{bot_id}/vote\nVerified votes award 90 coins, 2 energy and one card every 12 hours."
            if bot_id
            else "Top.gg is not configured for this installation.",
        )

    @app_commands.command(name="useitem", description="Use an energy booster or cosmetic badge")
    async def useitem(self, i: discord.Interaction, item: str):
        await self.defer(i)
        await self.app.economy.use_item(i.user.id, item, str(i.id))
        await send(i, "Items", "Item used.")

    @app_commands.command(
        name="favorite", description="Protect or unprotect a card from bulk system sale"
    )
    async def favorite(self, i: discord.Interaction, code: str, enabled: bool = True):
        await self.defer(i)
        async with self.app.db.transaction() as tx:
            card = await self.app.cards.available(tx, i.user.id, code)
            await tx.execute(
                "UPDATE owned_cards SET favorite=:v WHERE id=:id", v=int(enabled), id=card["id"]
            )
        await send(i, "Favorite", "Preference saved.")
