"""Offline wall-clock soak. Use a disposable database, never a production path."""

import argparse
import asyncio
import gc
import json
import sys
import tempfile
import time
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from gumabot.app import Application
from gumabot.config import Settings
from gumabot.database.migrations import check
from gumabot.utils.clock import Clock


class SimulationClock(Clock):
    def __init__(self):
        self.value = 1800000000

    def now(self):
        return datetime.fromtimestamp(self.value, UTC)


async def run(seconds, interval, memory_limit_mb):
    with tempfile.TemporaryDirectory(prefix="gumabot-soak-") as folder:
        clock = SimulationClock()
        app = Application(Settings(database=Path(folder) / "soak.db"), clock)

        # Any accidental external request fails immediately, rather than reaching a live provider.
        def offline(request):
            raise RuntimeError("Network access is forbidden in the offline soak")

        await app.http.aclose()
        app.http = httpx.AsyncClient(transport=httpx.MockTransport(offline))
        app.provider.client = app.http
        app.images.client = app.http
        try:
            await app.initialize()
            async with app.db.transaction() as tx:
                await tx.execute("INSERT INTO card_sets VALUES ('soak','Soak',8,NULL,0)")
                for rank in range(8):
                    await tx.execute(
                        "INSERT INTO card_catalog VALUES (:id,:id,:id,'soak',:r,:m)",
                        id=f"soak-{rank}",
                        r=rank,
                        m=json.dumps({"rarity": str(rank), "set_name": "Soak", "hp": 10 + rank}),
                    )
            for uid in (1, 2):
                await app.cards.start(uid, "soak")
            tracemalloc.start()
            baseline = None
            tasks = len(asyncio.all_tasks())
            started = time.monotonic()
            cycles = 0
            while time.monotonic() - started < seconds:
                async with asyncio.timeout(30):
                    clock.value += 86401
                    await asyncio.gather(app.economy.daily(1), app.economy.daily(2))
                    pack = await app.cards.open_pack(1, "soak", f"soak:{cycles}")
                    listing = await app.market.list_card(1, pack["cards"][0]["code"], 5)
                    await app.market.buy(2, listing)
                    trade = await app.trades.invite(1, 2)
                    await app.trades.accept(2, trade)
                    await app.trades.add(1, trade, "coins", amount=5)
                    await app.trades.confirm(1, trade)
                    await app.trades.confirm(2, trade)
                    auction = await app.auctions.create(1, pack["cards"][1]["code"], 5, hours=1)
                    await app.auctions.bid(2, auction, 5)
                    clock.value += 3601
                    await app.auctions.settle_due()
                    for operation in (
                        app.trades.expire,
                        app.claims.expire,
                        app.gameplay.expire,
                        app.grading.complete_due,
                    ):
                        await operation()
                cycles += 1
                gc.collect()
                current, peak = tracemalloc.get_traced_memory()
                if baseline is None and cycles >= 5:
                    baseline = current
                growth = max(0, current - (baseline or current))
                if growth > memory_limit_mb * 1024**2 or len(asyncio.all_tasks()) > tasks + 5:
                    raise RuntimeError("Soak resource budget exceeded")
                if app.provider.inflight or app.db.engine.pool.checkedout() != 0:
                    raise RuntimeError("Leaked provider task or database connection")
                if cycles % 60 == 0:
                    print(
                        json.dumps(
                            {
                                "cycles": cycles,
                                "elapsed_s": time.monotonic() - started,
                                "heap_bytes": current,
                                "peak_bytes": peak,
                                "tasks": len(asyncio.all_tasks()),
                            }
                        ),
                        flush=True,
                    )
                await asyncio.sleep(interval)
            await asyncio.to_thread(check, app.settings.database)
            print(
                json.dumps(
                    {
                        "status": "passed",
                        "cycles": cycles,
                        "elapsed_s": time.monotonic() - started,
                        "heap_growth_bytes": growth if cycles else 0,
                        "scope": "offline services; no Discord/reconnect validation",
                    }
                ),
                flush=True,
            )
        finally:
            tracemalloc.stop()
            await app.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=86400)
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument("--memory-limit-mb", type=int, default=64)
    args = parser.parse_args()
    if args.seconds <= 0 or args.interval < 0 or args.memory_limit_mb <= 0:
        parser.error("Duration/memory must be positive and interval nonnegative")
    asyncio.run(run(args.seconds, args.interval, args.memory_limit_mb))
