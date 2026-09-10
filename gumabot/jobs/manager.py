import asyncio
import logging
import time

from .reminders import Reminders

log = logging.getLogger(__name__)


class Jobs:
    def __init__(self, bot):
        self.bot, self.app = bot, bot.app
        self.task = None
        self.reminder_worker = Reminders(bot)

    def start(self):
        if self.task and not self.task.done():
            return
        self.task = asyncio.create_task(self.run(), name="gumabot-jobs")

    async def tick(self):
        for operation in (
            self.app.grading.complete_due,
            self.app.auctions.settle_due,
            self.app.trades.expire,
            self.app.claims.expire,
            self.app.gameplay.expire,
            self.app.progression.rollover,
            self.reminders,
        ):
            started = time.monotonic()
            try:
                await operation()
            except Exception:
                log.exception(
                    "Background job failed: %s",
                    operation.__name__,
                    extra={"event": "worker_failure"},
                )
            finally:
                log.info(
                    "Worker operation",
                    extra={
                        "event": "worker_duration",
                        "operation": operation.__name__,
                        "duration_ms": (time.monotonic() - started) * 1000,
                    },
                )

    async def run(self):
        await self.bot.wait_until_ready()
        try:
            await self.app.provider.list_sets()
        except Exception:
            log.warning("Initial set-list refresh failed; lazy sync remains available")
        while True:
            await self.tick()
            await asyncio.sleep(45)

    async def reminders(self):
        await self.reminder_worker.run()

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
