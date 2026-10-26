"""KuzuDB Thread-safe connection wrapper with dedicated write-actor."""

import asyncio
import logging
import os
from collections import deque
from pathlib import Path
from typing import Any

try:
    import kuzudb
except ImportError:
    logging.warning("kuzudb not installed; falling back to stub mode")

    class KuzuClient:
        pass


logger = logging.getLogger(__name__)


class KuzuClient:
    """Thread-safe KùzuDB wrapper with dedicated write-queue actor."""

    _shared_instance: "KuzuClient | None" = None

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).mkdir(parents=True, exist_ok=True)
        self._conn: Any = None
        self._write_actor_task: asyncio.Task | None = None
        self._write_queue: deque[str] = deque()
        self._is_running = False

    @classmethod
    async def init(cls, db_path: str) -> "KuzuClient":
        if cls._shared_instance is not None:
            return cls._shared_instance
        client = cls(db_path)
        await client.connect()
        cls._shared_instance = client
        return client

    async def connect(self):
        try:
            self._conn = kuzudb.KuzuDB.get_instance(str(self.db_path))
            self._is_running = True
            self._write_actor_task = asyncio.create_task(self._run_write_actor())
            logger.info("Connected to KùzuDB at %s", self.db_path)
        except Exception as exc:
            logger.error("Failed to connect to KùzuDB: %s", exc)
            raise

    async def close(self):
        self._is_running = False
        if self._write_actor_task:
            self._write_actor_task.cancel()
        try:
            if self._conn:
                await self._conn.close()
        except Exception:
            pass
        self._conn = None
        logger.info("KùzuDB connection closed")

    async def enqueue_write(self, cypher: str, params: dict | None = None):
        """Enqueue a Cypher write operation for serialized execution."""
        self._write_queue.append((cypher, params))

    async def read(self, cypher: str, params: dict | None = None) -> list[Any]:
        """Execute a read-only Cypher query."""
        result = await self._execute(cypher, params, read_only=True)
        return result

    async def _execute(
        self, cypher: str, params: dict | None = None, read_only: bool = False
    ) -> list[Any]:
        try:
            if self._conn is None:
                raise RuntimeError("KùzuDB not initialized")
            if read_only:
                return await self._conn.read_only_cypher_query(cypher, params)
            else:
                return await self._conn.cypher_query(cypher, params)
        except Exception as exc:
            logger.error("Cypher execution error: %s", exc)
            raise

    async def _run_write_actor(self):
        """Background task that serializes all graph mutations."""
        while self._is_running:
            if self._write_queue:
                cypher, params = self._write_queue.popleft()
                try:
                    await self._conn.commit(cypher, params)
                except Exception as exc:
                    logger.error("Write failure: %s", exc)
            else:
                await asyncio.sleep(0.005)
