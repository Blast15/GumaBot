import asyncio
import hashlib
import io
import logging
import warnings
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 12_000_000
log = logging.getLogger(__name__)


class Images:
    def __init__(self, client, directory):
        self.client = client
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.limit = asyncio.Semaphore(3)
        self.render_limit = asyncio.Semaphore(2)
        self.inflight = {}

    @staticmethod
    def validate(data):
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if (
                    image.width > 4096
                    or image.height > 4096
                    or image.width * image.height > 12_000_000
                ):
                    raise ValueError("Image dimensions exceed limit")
                image.verify()
        return data

    async def _download(self, url):
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "assets.tcgdex.net"
            or parsed.port not in (None, 443)
            or parsed.username
        ):
            return None
        path = self.directory / (hashlib.sha256(url.encode()).hexdigest() + ".img")
        async with self.limit:
            if path.exists():
                try:
                    return await asyncio.to_thread(self.validate, path.read_bytes())
                except (
                    ValueError,
                    OSError,
                    UnidentifiedImageError,
                    Image.DecompressionBombError,
                    Image.DecompressionBombWarning,
                ):
                    path.unlink(missing_ok=True)
            try:
                async with asyncio.timeout(20):
                    async with self.client.stream("GET", url, follow_redirects=False) as response:
                        response.raise_for_status()
                        if response.headers.get("content-type", "").split(";")[0] not in (
                            "image/png",
                            "image/jpeg",
                            "image/webp",
                        ):
                            return None
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > 5_000_000:
                                return None
                    raw = await asyncio.to_thread(self.validate, bytes(data))
                    await asyncio.to_thread(path.write_bytes, raw)
                    return raw
            except Exception:
                log.warning("Card image unavailable; using placeholder")
                return None

    async def get(self, url):
        if not url:
            return None
        if url not in self.inflight:
            task = asyncio.create_task(self._download(url))
            self.inflight[url] = task
            task.add_done_callback(lambda _: self.inflight.pop(url, None))
        return await asyncio.shield(self.inflight[url])

    @staticmethod
    def compose(cards, blobs):
        width = min(3, max(1, len(cards))) * 300
        height = ((len(cards) + 2) // 3) * 450
        image = Image.new("RGB", (width, max(height, 450)), "#111B2E")
        draw = ImageDraw.Draw(image)
        for i, (card, blob) in enumerate(zip(cards, blobs, strict=True)):
            x, y = (i % 3) * 300, (i // 3) * 450
            draw.rounded_rectangle(
                (x + 6, y + 6, x + 294, y + 444),
                radius=12,
                fill="#263955",
                outline="#55BFAF",
                width=2,
            )
            draw.text(
                (x + 18, y + 15), "GumaBot · " + str(card.get("public_code", "")), fill="white"
            )
            if blob:
                with Image.open(io.BytesIO(blob)) as original:
                    face = ImageOps.contain(original.convert("RGB"), (260, 340))
                    if card.get("tint"):
                        face = Image.blend(face, Image.new("RGB", face.size, card["tint"]), 0.15)
                    image.paste(face, (x + (300 - face.width) // 2, y + 45))
            else:
                draw.text((x + 30, y + 190), "GumaBot\nCard image unavailable", fill="white")
            draw.text((x + 18, y + 390), str(card.get("name", "Card"))[:35], fill="white")
            draw.text(
                (x + 18, y + 410),
                f"{card.get('condition_name', '')} · Grade {card.get('grade') or 'Raw'}",
                fill="#BFE8E1",
            )
            if card.get("certificate"):
                draw.text(
                    (x + 18, y + 430),
                    "C {:.1f}  Co {:.1f}  E {:.1f}  S {:.1f}".format(
                        card["centering"], card["corners"], card["edges"], card["surface"]
                    ),
                    fill="#BFE8E1",
                )
        output = io.BytesIO()
        image.save(output, format="PNG")
        output.seek(0)
        return output

    async def render(self, cards):
        cards = cards[:9]
        blobs = await asyncio.gather(*(self.get(c.get("image_url")) for c in cards))
        async with self.render_limit:
            return await asyncio.to_thread(self.compose, cards, blobs)

    async def close(self):
        tasks = list(self.inflight.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
