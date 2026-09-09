import hashlib
import hmac
import json

from aiohttp import web


class Webhook:
    def __init__(self, app):
        self.app = app
        self.runner = None

    async def health(self, request):
        async with self.app.db.read() as tx:
            await tx.one("SELECT 1 AS ok")
        return web.json_response({"status": "ok"})

    async def vote(self, request):
        raw = await request.read()
        version = self.app.settings.webhook_version
        if version == "v1":
            try:
                fields = dict(
                    part.strip().split("=", 1)
                    for part in request.headers.get("x-topgg-signature", "").split(",")
                )
                stamp = fields["t"]
                if abs(int(stamp) - self.app.clock.timestamp()) > 300:
                    raise ValueError()
                expected = hmac.new(
                    self.app.settings.webhook_secret.encode(),
                    stamp.encode() + b"." + raw,
                    hashlib.sha256,
                ).hexdigest()
                if not hmac.compare_digest(expected, fields["v1"]):
                    raise ValueError()
            except (KeyError, ValueError):
                raise web.HTTPUnauthorized() from None
        elif not hmac.compare_digest(
            request.headers.get("Authorization", ""), self.app.settings.webhook_secret
        ):
            raise web.HTTPUnauthorized()
        try:
            payload = json.loads(raw)
            if payload.get("type") == ("webhook.test" if version == "v1" else "test"):
                return web.json_response({"test": True})
            if version == "v1":
                if payload["type"] != "vote.create":
                    raise ValueError()
                data = payload["data"]
                project = data["project"]
                if (
                    project["platform_id"] != self.app.settings.topgg_bot_id
                    or project["platform"] != "discord"
                    or project["type"] != "bot"
                ):
                    raise ValueError()
                uid, event_id = int(data["user"]["platform_id"]), "topgg:" + str(data["id"])
            else:
                if payload["type"] != "upvote" or payload["bot"] != self.app.settings.topgg_bot_id:
                    raise ValueError()
                uid = int(payload["user"])
                event_id = f"topgg-v0:{uid}:{self.app.clock.timestamp() // 43200}"
            if not 0 < uid < 2**63 or len(event_id) > 150:
                raise ValueError()
        except (ValueError, KeyError, TypeError, AttributeError):
            raise web.HTTPBadRequest() from None
        # Persist before acknowledging; API calls happen in the restart-safe worker.
        async with self.app.db.transaction() as tx:
            await tx.execute(
                "INSERT INTO vote_inbox(id,user_id,received_at) VALUES (:id,:u,:t) ON CONFLICT DO NOTHING",
                id=event_id,
                u=uid,
                t=self.app.clock.timestamp(),
            )
        return web.json_response({"accepted": True})

    async def start(self):
        application = web.Application(client_max_size=8192)
        application.router.add_get("/health", self.health)
        application.router.add_post("/webhooks/topgg", self.vote)
        self.runner = web.AppRunner(application)
        await self.runner.setup()
        await web.TCPSite(
            self.runner, self.app.settings.webhook_host, self.app.settings.webhook_port
        ).start()

    async def close(self):
        if self.runner:
            await self.runner.cleanup()
