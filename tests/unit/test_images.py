import io

import httpx
from PIL import Image

from gumabot.rendering.images import Images


def png():
    out = io.BytesIO()
    Image.new("RGB", (100, 140), "red").save(out, format="PNG")
    return out.getvalue()


async def test_image_cache_validation_and_placeholder(tmp_path):
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(200, content=png(), headers={"content-type": "image/png"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        images = Images(client, tmp_path)
        url = "https://assets.tcgdex.net/en/test/high.png"
        assert await images.get(url) == png()
        assert await images.get(url) == png()
        assert len(calls) == 1
        path = next(tmp_path.iterdir())
        path.write_bytes(b"broken")
        assert await images.get(url) == png()
        assert len(calls) == 2
        assert await images.get("http://127.0.0.1/secrets") is None
        assert await images.get("https://example.com/test") is None
        assert await images.get(None) is None
        result = await images.render(
            [{"name": "Test", "image_url": url, "tint": "#336699", "grade": 9}, {"name": "Missing"}]
        )
        with Image.open(result) as image:
            assert image.size == (600, 450)
        await images.close()


async def test_image_rejects_bad_content_and_large_payload(tmp_path):
    for headers, body in [
        ({"content-type": "text/html"}, b"bad"),
        ({"content-type": "image/png"}, b"not an image"),
        ({"content-type": "image/png"}, b"x" * 5_000_001),
    ]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, headers=headers, content=body)
            )
        ) as client:
            images = Images(client, tmp_path)
            assert await images.get("https://assets.tcgdex.net/bad.png") is None
