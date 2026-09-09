import itertools
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from conftest import mint, users

from gumabot.bot import GumaBot
from gumabot.views.ui import GUIDE, GuessModal, ReportModal, embed

ids = itertools.count(10000)


class Interaction:
    def __init__(self, uid=1, custom=None):
        self.id = next(ids)
        self.user = SimpleNamespace(id=uid, bot=False)
        self.guild_id = 123
        self.type = (
            discord.InteractionType.component
            if custom
            else discord.InteractionType.application_command
        )
        self.data = {"custom_id": custom} if custom else {"name": "test"}
        self.response = SimpleNamespace(
            defer=AsyncMock(),
            send_message=AsyncMock(),
            send_modal=AsyncMock(),
            is_done=lambda: True,
        )
        self.followup = SimpleNamespace(send=AsyncMock())
        self.message = SimpleNamespace(edit=AsyncMock())


async def invoke(cog, command_name, uid=1, **kwargs):
    interaction = Interaction(uid)
    await getattr(cog, command_name).callback(cog, interaction, **kwargs)
    assert interaction.followup.send.called or interaction.response.send_modal.called
    return interaction


async def test_collection_economy_commands_and_dashboard(app):
    async with GumaBot(app) as bot:
        await bot.register()
        cog = bot.get_cog("GameCommands")
        await invoke(cog, "start")
        await invoke(cog, "start", uid=2)
        for command in ("play", "help", "guide", "daily", "openpack", "buypack", "resetpack"):
            await invoke(cog, command)
        await invoke(cog, "inventory")
        await invoke(cog, "inventory", name="Card", sort="rarity")
        await invoke(cog, "find", name="Card")
        assert await cog.find_autocomplete(Interaction(), "Card")
        code = (await app.cards.inventory(1))[0]["public_code"]
        await invoke(cog, "search", code=code)
        async with app.db.transaction() as tx:
            await app.cards.money(tx, 1, 10000, "TEST", "fund")
        await invoke(cog, "buyitem", item="box")
        await invoke(cog, "mysterybox")
        await invoke(cog, "give", user=SimpleNamespace(id=2, bot=False), amount=5)
        await invoke(cog, "buyitem", item="tint")
        await invoke(cog, "tint", code=code, color="#336699")
        codes = [await mint(app) for _ in range(3)]
        await invoke(cog, "swapcodes", first=codes[0], second=codes[1])
        await invoke(cog, "fuse", code1=codes[0], code2=codes[1], code3=codes[2])
        await invoke(cog, "grade", code=code)
        await invoke(cog, "checkgrade", code=code)
        await invoke(cog, "cardtrend", card_id="test-0")
        await invoke(cog, "avatarchoice", avatar="Ranger")
        await invoke(cog, "leaderboard")
        await invoke(cog, "reminder", kind="daily", enabled=True)
        await invoke(cog, "report")
        await invoke(
            cog, "setchannel", channel=SimpleNamespace(id=456, guild=SimpleNamespace(id=123))
        )
        await invoke(cog, "sell")
        await invoke(cog, "peek", code=await mint(app))
        for name in (
            "balance",
            "level",
            "collection",
            "setcompletion",
            "missing",
            "items",
            "itemshop",
            "bag",
            "quizstats",
            "duelprofile",
            "achievements",
            "quests",
            "season",
            "serverleaderboard",
            "cooldowns",
            "upcoming",
        ):
            i = Interaction()
            await bot.tree.get_command(name).callback(i)
            assert i.followup.send.called


async def test_game_commands_and_persisted_components(app):
    await users(app)
    for uid in (1, 2):
        codes = [await mint(app, uid, "test-7") for _ in range(5)]
        await app.gameplay.deck(uid, codes)
    async with GumaBot(app) as bot:
        await bot.register()
        cog = bot.get_cog("GameCommands")
        await invoke(cog, "deck")
        await invoke(cog, "gym")
        await invoke(cog, "journey")
        await invoke(cog, "blackjack")
        await invoke(cog, "quiz")
        await invoke(cog, "pickcard")
        await invoke(cog, "duel", user=SimpleNamespace(id=2, bot=False))
        async with app.db.read() as tx:
            duel = await tx.one("SELECT id FROM duels LIMIT 1")
        await bot.on_interaction(Interaction(2, "gb:duelaccept:" + duel["id"]))
        await bot.on_interaction(Interaction(1, f"gb:duel:{duel['id']}:attack:0"))
        await invoke(cog, "duel", duel_id=duel["id"])
        await invoke(cog, "trade", user=SimpleNamespace(id=2, bot=False))
        async with app.db.read() as tx:
            trade = await tx.one("SELECT id FROM trades LIMIT 1")
        key = trade["id"]
        await invoke(cog, "trade", uid=2, trade_id=key, action="accept")
        await invoke(cog, "trade", trade_id=key, action="add", kind="coins", amount=10)
        await invoke(cog, "trade", trade_id=key, action="confirm")
        await invoke(cog, "trade", uid=2, trade_id=key, action="confirm")
        for route in (
            "inventory:1:0",
            "guide:1:2",
            "dashboard:1",
            "dash:1:inventory",
            "dash:1:market",
            "dash:1:battle",
            "dash:1:quests",
            "dash:1:guide",
            "rank:1:coins:0",
            "close:1",
        ):
            i = Interaction(1, "gb:" + route)
            await bot.on_interaction(i)
            assert i.followup.send.called
        i = Interaction(2, "gb:inventory:1:0")
        await bot.on_interaction(i)
        assert "another player" in i.followup.send.call_args.kwargs["embed"].description
        await bot.on_interaction(Interaction(1))


async def test_market_auction_wishlist_groups(app):
    await users(app)
    async with GumaBot(app) as bot:
        await bot.register()
        market = bot.tree.get_command("market")
        auction = bot.tree.get_command("auction")
        code = await mint(app)
        await invoke(market, "list_card", code=code, price=20)
        await invoke(market, "browse")
        listing = (await app.market.browse())[0]["id"]
        await invoke(market, "buy", uid=2, listing=listing)
        await invoke(market, "list_card", code=await mint(app), price=20)
        listing = (await app.market.browse())[0]["id"]
        await invoke(market, "remove", listing=listing)
        await invoke(auction, "create", code=await mint(app), price=20)
        async with app.db.read() as tx:
            key = (await tx.one("SELECT id FROM auctions"))["id"]
        await invoke(auction, "info", auction=key)
        await invoke(auction, "bid", uid=2, auction=key, amount=20)
        await invoke(auction, "create", code=await mint(app), price=20)
        async with app.db.read() as tx:
            key = (await tx.one("SELECT id FROM auctions WHERE bidder IS NULL"))["id"]
        await invoke(auction, "cancel", auction=key)
        wishlist = bot.tree.get_command("wishlist")
        await invoke(wishlist, "list_cards")
        await invoke(wishlist, "remove", card_id="test-0")


async def test_component_claims_and_sessions(app):
    await users(app)
    async with GumaBot(app) as bot:
        await bot.register()
        listing = await app.market.list_card(1, await mint(app), 10)
        await bot.on_interaction(Interaction(2, "gb:buy:" + listing))
        await mint(app)
        peek = await app.claims.peek(1, await mint(app))
        await bot.on_interaction(Interaction(2, "gb:peek:" + peek))
        async with app.db.transaction() as tx:
            await tx.execute("INSERT INTO guilds(id,drop_enabled) VALUES (123,1)")
        drop = await app.claims.create_drop(123, "test-0")
        await bot.on_interaction(Interaction(2, "gb:drop:" + drop))
        key = await app.gameplay.new_session(1, "quiz")
        await bot.on_interaction(Interaction(1, f"gb:session:{key}:0:0"))
        key = await app.gameplay.new_session(1, "pickcard", "test")
        await bot.on_interaction(Interaction(1, f"gb:session:{key}:0:0"))
        await bot.on_interaction(Interaction(1, "gb:journey:1:explore"))
        trade = await app.trades.invite(1, 2)
        await bot.on_interaction(Interaction(2, "gb:trade:" + trade + ":accept"))
        await bot.on_interaction(Interaction(1, "gb:trade:" + trade + ":cancel"))
        i = Interaction(1, "gb:guess:key")
        await bot.on_interaction(i)
        assert i.response.send_modal.called
        cog = bot.get_cog("GameCommands")
        result = await invoke(cog, "sell")
        custom = result.followup.send.call_args.kwargs["view"].children[0].custom_id
        await bot.on_interaction(Interaction(1, custom))
        await bot.on_interaction(Interaction(1, custom))


async def test_ui_modals_error_handling_and_image_showcase(app, tmp_path):
    from gumabot.rendering.images import Images
    from gumabot.services.errors import DomainError

    await users(app)
    app.images = Images(app.http, tmp_path / "images")
    await mint(app)
    async with GumaBot(app) as bot:
        await bot.register()
        cog = bot.get_cog("GameCommands")
        await invoke(cog, "showcase")
        i = Interaction()
        await bot.command_error(i, DomainError("Friendly error"))
        assert i.followup.send.call_args.kwargs["embed"].description == "Friendly error"
        await bot.command_error(i, discord.app_commands.CheckFailure())
        await bot.command_error(i, RuntimeError("internal error"))
        assert "internal error" not in i.followup.send.call_args.kwargs["embed"].description
        modal = ReportModal(app)
        modal.body._value = "This is a useful report."
        await modal.on_submit(Interaction())
        key = await app.gameplay.new_session(1, "namepokemon", "test")
        modal = GuessModal(app, key)
        modal.answer._value = "Wrong"
        await modal.on_submit(Interaction())
        await modal.on_submit(Interaction())
        assert len(GUIDE) == 7
        assert len(embed("title", "x" * 10000).description) == 3900
    await app.images.close()


async def test_pack_reveal_set_selector_and_fuzzy_find(app, tmp_path):
    from gumabot.rendering.images import Images
    from gumabot.views.ui import reveal_pack, show_sets

    app.images = Images(app.http, tmp_path / "images")
    await users(app)
    result = await app.cards.open_pack(1, "test", "saved-pack")
    await reveal_pack(Interaction(), app, result["pack"])
    assert await app.cards.find(1, "Crd 0")
    async with app.db.transaction() as tx:
        await tx.execute(
            "INSERT INTO provider_cache VALUES (:k,:p,:t)",
            k=app.provider.base + "/sets",
            p=json.dumps([{"id": "test", "name": "Test"}]),
            t=app.clock.timestamp() + 86400,
        )
    await show_sets(Interaction(), app)
    async with GumaBot(app) as bot:
        await bot.register()
        i = Interaction(1, "gb:sets:1:0")
        await bot.on_interaction(i)
        assert (
            i.followup.send.call_args.kwargs["view"].children[-1].type
            == discord.ComponentType.string_select
        )
        i = Interaction(1, "gb:setpick:1")
        i.data["values"] = ["test"]
        await bot.on_interaction(i)
        assert "cards" in i.followup.send.call_args.kwargs["embed"].description
        await bot.on_interaction(Interaction(1, "gb:reveal:1:saved-pack"))
    await app.images.close()


async def test_certificate_favorite_and_item_actions(app, tmp_path):
    from gumabot.rendering.images import Images

    app.images = Images(app.http, tmp_path / "images")
    await users(app)
    code = await mint(app)
    async with GumaBot(app) as bot:
        await bot.register()
        cog = bot.get_cog("GameCommands")
        await invoke(cog, "favorite", code=code)
        assert not await app.market.sell_preview(1)
        await invoke(cog, "buyitem", item="booster")
        await invoke(cog, "useitem", item="booster")
        await app.grading.submit(1, code, "express")
        app.clock.advance(21601)
        await app.grading.complete_due()
        result = await invoke(cog, "checkgrade", code=code)
        assert result.followup.send.call_args.kwargs["file"].filename == "gumabot-certificate.png"
    await app.images.close()
