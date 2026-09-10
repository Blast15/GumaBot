import json
import logging

import discord

from ..services.engines import blackjack_total
from ..services.errors import DomainError
from ..services.quiz import question_at

log = logging.getLogger(__name__)


def embed(title, value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return discord.Embed(
        title=title[:256], description=str(value or "No results.")[:3900], color=0x55BFAF
    )


def buttons(specs):
    view = discord.ui.View(timeout=None)
    for label, custom in specs[:25]:
        view.add_item(
            discord.ui.Button(
                label=label[:80], custom_id="gb:" + custom, style=discord.ButtonStyle.secondary
            )
        )
    return view


async def send(interaction, title, value, view=None, ephemeral=True, file=None):
    kwargs = {
        "embed": embed(title, value),
        "ephemeral": ephemeral,
        "allowed_mentions": discord.AllowedMentions.none(),
    }
    if view is not None:
        kwargs["view"] = view
    if file is not None:
        kwargs["file"] = file
    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)


GUIDE = [
    "Run /start once: 150 coins and a free five-card pack with a guaranteed Holo. /play opens your dashboard.",
    "Use /openpack with an optional set ID. Each pack has five cards. God Packs contain only Holo-or-higher cards. Odds are GumaBot game odds, not physical booster odds.",
    "Natural energy regenerates one point every two hours, up to three. /buypack adds one energy for 40 coins. Purchased energy can exceed the natural cap.",
    "Explore /inventory, /collection and /missing. Public codes identify individual cards. Fusion consumes three raw duplicates to improve condition.",
    "Submit /grade in economy, standard, fast or express lanes. Four subgrades produce a grade from 1 to 10. Locked cards cannot be transferred.",
    "Claim /daily once every rolling 24 hours. Use /market, /auction and /trade. Auction bids and trade offers reserve funds immediately.",
    "Create a five-card /deck. Duel players, challenge eight /gym leaders, answer /quiz and explore /journey. Check /quests, /level and /season.",
]


class ReportModal(discord.ui.Modal, title="GumaBot feedback"):
    body: discord.ui.TextInput = discord.ui.TextInput(
        label="Bug or feedback", style=discord.TextStyle.paragraph, min_length=10, max_length=2000
    )

    def __init__(self, app):
        super().__init__()
        self.app = app

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.app.progression.report(interaction.user.id, str(self.body))
            await send(interaction, "Report", "Saved. Thank you.")
        except DomainError as exc:
            await send(interaction, "Report", str(exc))


class GuessModal(discord.ui.Modal, title="Name the Pokémon"):
    answer: discord.ui.TextInput = discord.ui.TextInput(label="Pokémon name", max_length=100)

    def __init__(self, app, key):
        super().__init__()
        self.app, self.key = app, key

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.app.gameplay.session_action(
                interaction.user.id, self.key, str(self.answer)
            )
            await send(interaction, "Your answer", result)
        except DomainError as exc:
            await send(interaction, "Game", str(exc))


async def show_session(interaction, app, key):
    async with app.db.read() as tx:
        row = await tx.one(
            "SELECT * FROM quiz_attempts WHERE id=:id AND user_id=:u AND completed=0",
            id=key,
            u=interaction.user.id,
        )
    if not row:
        raise DomainError("Session finished or unavailable.")
    state, kind = json.loads(row["state"]), row["kind"]
    if kind == "quiz":
        pos = state["position"]
        question, options, _ = question_at(state, pos)
        await send(
            interaction,
            f"Quiz {pos + 1}/10",
            question,
            buttons([(text, f"session:{key}:{i}:{pos}") for i, text in enumerate(options)]),
        )
    elif kind == "blackjack":
        await send(
            interaction,
            "Blackjack",
            f"Your cards: {state['player']} (total {blackjack_total(state['player'])})\nDealer showing: {state['dealer'][0]}",
            buttons(
                [(a.title(), f"session:{key}:{a}:{len(state['player'])}") for a in ("hit", "stand")]
            ),
        )
    elif kind == "pickcard":
        async with app.db.read() as tx:
            cards = [
                await tx.one("SELECT name FROM card_catalog WHERE id=:id", id=c)
                for c in state["choices"]
            ]
        await send(
            interaction,
            "Choose one card",
            "Choose carefully; only one claim is allowed.",
            buttons([(c["name"], f"session:{key}:{i}:0") for i, c in enumerate(cards)]),
        )
    else:
        async with app.db.read() as tx:
            card = await tx.one("SELECT metadata FROM card_catalog WHERE id=:id", id=state["card"])
        blob = await app.images.get(json.loads(card["metadata"])["image_url"])
        if not blob:
            raise DomainError(
                "Image unavailable. Your session remains available with /namepokemon session."
            )
        import io

        await send(
            interaction,
            "Name this Pokémon",
            "What is its name?",
            buttons([("Answer", f"guess:{key}")]),
            file=discord.File(io.BytesIO(blob), filename="challenge.webp"),
        )


async def show_duel(interaction, app, key):
    async with app.db.read() as tx:
        row = await tx.one(
            "SELECT * FROM duels WHERE id=:id AND (challenger=:u OR opponent=:u)",
            id=key,
            u=interaction.user.id,
        )
    if not row:
        raise DomainError("Duel not found.")
    state = json.loads(row["state"])
    specs = (
        [("Accept", f"duelaccept:{key}")]
        if row["status"] == "invited"
        else [
            (a.title(), f"duel:{key}:{a}:{state['turn']}")
            for a in ("attack", "defend", "heal", "rarity")
        ]
        if row["status"] == "active"
        else []
    )
    await send(
        interaction,
        f"Duel {key}",
        {
            "status": row["status"],
            "challenger": row["challenger"],
            "opponent": row["opponent"],
            **state,
        },
        buttons(specs),
        ephemeral=False,
    )


async def show_sets(interaction, app, page=0):
    sets = await app.provider.list_sets()
    page = max(0, min(page, max(0, (len(sets) - 1) // 25)))
    selected = sets[page * 25 : page * 25 + 25]
    view = buttons(
        [
            ("Previous", f"sets:{interaction.user.id}:{max(0, page - 1)}"),
            ("Next", f"sets:{interaction.user.id}:{page + 1}"),
        ]
    )
    if selected:
        view.add_item(
            discord.ui.Select(
                placeholder="Choose a set and open a pack",
                custom_id=f"gb:setpick:{interaction.user.id}",
                options=[
                    discord.SelectOption(label=s["name"][:100], value=s["id"]) for s in selected
                ],
            )
        )
    await send(
        interaction,
        f"Packs · page {page + 1}",
        "Choose a set below. Opening costs one energy. First use may take longer while the catalog is cached.",
        view,
    )


async def reveal_pack(interaction, app, key):
    async with app.db.read() as tx:
        row = await tx.one(
            "SELECT * FROM pack_openings WHERE id=:id AND user_id=:u", id=key, u=interaction.user.id
        )
        if not row:
            raise DomainError("Pack not found.")
        rows = await tx.all(
            "SELECT p.public_code,c.name,c.metadata FROM pack_pulls p JOIN card_catalog c ON c.id=p.catalog_card_id WHERE p.opening_id=:id ORDER BY p.slot",
            id=key,
        )
    for card in rows:
        card["image_url"] = json.loads(card.pop("metadata"))["image_url"]
    try:
        image = await app.images.render(rows)
        await send(
            interaction, "Your pack", rows, file=discord.File(image, filename="gumabot-pack.png")
        )
    except (OSError, ValueError):
        await send(interaction, "Your pack", rows)
