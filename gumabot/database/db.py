import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from .migrations import migrate


class Transaction:
    def __init__(self, connection):
        self.connection = connection

    async def execute(self, sql: str, **params):
        return await self.connection.execute(text(sql), params)

    async def one(self, sql: str, **params):
        result = await self.execute(sql, **params)
        row = result.mappings().first()
        return dict(row) if row else None

    async def all(self, sql: str, **params):
        result = await self.execute(sql, **params)
        return [dict(row) for row in result.mappings()]


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.engine = create_async_engine(
            URL.create("sqlite+aiosqlite", database=str(path)), pool_size=5, max_overflow=0
        )

        @event.listens_for(self.engine.sync_engine, "connect")
        def configure(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    async def initialize(self):
        await asyncio.to_thread(migrate, self.path)

    @asynccontextmanager
    async def transaction(self):
        async with self.engine.connect() as connection:
            started = time.monotonic()
            try:
                await connection.execute(text("BEGIN IMMEDIATE"))
            except OperationalError:
                logging.getLogger(__name__).exception(
                    "SQLite transaction could not begin", extra={"event": "db_begin_error"}
                )
                raise
            logging.getLogger(__name__).debug(
                "SQLite writer acquired",
                extra={
                    "event": "db_writer_wait",
                    "duration_ms": (time.monotonic() - started) * 1000,
                },
            )
            try:
                yield Transaction(connection)
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise

    @asynccontextmanager
    async def read(self):
        async with self.engine.connect() as connection:
            yield Transaction(connection)

    async def close(self):
        await self.engine.dispose()
