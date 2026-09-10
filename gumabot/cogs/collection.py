import json

import discord
from discord import app_commands

from ..services.errors import DomainError
from ..services.rules import Rarity
from ..views.ui import buttons, send
from .base import CommandBase


class CollectionCommands(CommandBase):
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
