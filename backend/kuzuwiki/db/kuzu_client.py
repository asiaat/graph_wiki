"""KùzuDB access layer.

The embedded Kùzu engine is not thread-safe and a connection belongs to the
thread that opened it. We therefore pin every statement to a single dedicated
worker thread and funnel all access through it. That gives us, for free:

* serialization of writes (no interleaved MERGE/MATCH races),
* a non-blocking event loop (queries run off the loop thread),
* deterministic error propagation instead of fire-and-forget queues.

The public surface is intentionally small::

    rows = await client.read("MATCH (e:Entity) RETURN e")
    await client.write("MERGE (e:Entity {id: $id}) SET e.x = $x", {...})

``enqueue_write`` is kept as an alias of ``write`` for callers that were
written against the older queue-based contract.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import kuzu

logger = logging.getLogger(__name__)


class KuzuError(RuntimeError):
    """Raised when a statement cannot be executed."""


class KuzuClient:
    """Async facade over a single-threaded embedded Kùzu connection."""

    _shared_instance: KuzuClient | None = None

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        self._executor: ThreadPoolExecutor | None = None
        self._db: kuzu.Database | None = None
        self._conn: kuzu.Connection | None = None
        self._is_running = False

    # ------------------------------------------------------------------ setup

    @classmethod
    async def init(cls, db_path: str) -> KuzuClient:
        if cls._shared_instance is not None and cls._shared_instance._is_running:
            return cls._shared_instance
        client = cls(db_path)
        await client.connect()
        cls._shared_instance = client
        return client

    async def connect(self) -> KuzuClient:
        parent = Path(self.db_path).parent
        if parent.exists() and not parent.is_dir():
            raise KuzuError(
                f"Cannot create the KùzuDB directory {parent}: it exists as a file. "
                f"Point KUZU_DB_PATH at a file inside a directory, e.g. {parent}/graph.kuzu"
            )
        parent.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kuzu")
        loop = asyncio.get_running_loop()
        # The connection is created *inside* the worker thread so that it stays
        # bound to that thread for its whole lifetime.
        await loop.run_in_executor(self._executor, self._open_connection)
        self._is_running = True
        logger.info("Connected to KùzuDB at %s", self.db_path)
        return self

    def _open_connection(self) -> None:
        self._db = kuzu.Database(self.db_path)
        self._conn = kuzu.Connection(self._db)

    async def close(self) -> None:
        self._is_running = False
        if self._executor is not None:
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(self._executor, self._close_connection)
            except Exception:  # pragma: no cover - shutdown best effort
                logger.debug("Error while closing Kùzu connection", exc_info=True)
            self._executor.shutdown(wait=True)
            self._executor = None
        self._conn = None
        self._db = None
        if KuzuClient._shared_instance is self:
            KuzuClient._shared_instance = None
        logger.info("KùzuDB connection closed")

    def _close_connection(self) -> None:
        if self._conn is not None:
            self._conn.close()
        if self._db is not None:
            self._db.close()

    # -------------------------------------------------------------- execution

    async def read(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a read statement and return rows as plain dictionaries."""
        return await self._run(cypher, params)

    async def write(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a write statement. Awaiting it guarantees the write landed."""
        return await self._run(cypher, params)

    async def enqueue_write(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Backwards-compatible alias for :meth:`write`."""
        return await self._run(cypher, params)

    async def _run(self, cypher: str, params: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not self._is_running or self._executor is None:
            raise KuzuError("KùzuDB client is not connected")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._execute, cypher, params)

    def _execute(self, cypher: str, params: dict[str, Any] | None) -> list[dict[str, Any]]:
        if self._conn is None:
            raise KuzuError("KùzuDB connection is not initialised")
        try:
            result = self._conn.execute(cypher, params or {})
            # ``rows_as_dict()`` switches the result formatting and returns the
            # QueryResult itself, so it must be called *before* iterating.
            result.rows_as_dict()
            rows: list[dict[str, Any]] = []
            while result.has_next():
                rows.append(result.get_next())
            return rows
        except Exception as exc:
            first_line = cypher.strip().splitlines()[0] if cypher.strip() else cypher
            logger.error("Kùzu statement failed: %s | %s", first_line, exc)
            raise KuzuError(str(exc)) from exc

    # ----------------------------------------------------------------- helpers

    async def table_names(self) -> set[str]:
        rows = await self.read("CALL show_tables() RETURN *")
        return {str(row["name"]) for row in rows if row.get("name")}

    async def index_names(self) -> set[str]:
        rows = await self.read("CALL show_indexes() RETURN *")
        return {str(row["index_name"]) for row in rows if row.get("index_name")}
