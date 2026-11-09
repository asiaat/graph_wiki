"""Project registry and isolated KùzuDB runtime management."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kuzuwiki.agents.orchestrator import Orchestrator
from kuzuwiki.config import settings
from kuzuwiki.db.kuzu_client import KuzuClient
from kuzuwiki.db.schema_init import ensure_schema
from kuzuwiki.db.wiki_sync import WikiSync

DEFAULT_LAYOUT: dict[str, Any] = {
    "version": 1,
    "panels": [
        {"id": "graph-overview", "width": "wide"},
        {"id": "attack-index", "width": "wide"},
        {"id": "entity-categories", "width": "half"},
        {"id": "source-reliability", "width": "half"},
        {"id": "claim-confidence", "width": "half"},
    ],
}


class ProjectStore:
    """Small durable metadata store; graph data itself stays in per-project KùzuDB files."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    dashboard_layout TEXT NOT NULL
                )"""
            )
            project_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(projects)").fetchall()
            }
            if "archived_at" not in project_columns:
                connection.execute("ALTER TABLE projects ADD COLUMN archived_at TEXT")
            connection.execute(
                "INSERT OR IGNORE INTO projects (id, name, dashboard_layout) VALUES (?, ?, ?)",
                ("default", "Default Project", json.dumps(DEFAULT_LAYOUT)),
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS project_links (
                    id TEXT PRIMARY KEY,
                    from_project_id TEXT NOT NULL REFERENCES projects(id),
                    from_entity_id TEXT NOT NULL,
                    from_entity_name TEXT NOT NULL,
                    to_project_id TEXT NOT NULL REFERENCES projects(id),
                    to_entity_id TEXT NOT NULL,
                    to_entity_name TEXT NOT NULL,
                    link_kind TEXT NOT NULL,
                    rationale TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (from_project_id, from_entity_id, to_project_id, to_entity_id, link_kind)
                )"""
            )

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        project = dict(row)
        project["dashboard_layout"] = json.loads(project["dashboard_layout"])
        return project

    def list_projects(self, include_archived: bool = False) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, name, created_at, dashboard_layout, archived_at FROM projects "
                "WHERE ? OR archived_at IS NULL "
                "ORDER BY CASE WHEN id = 'default' THEN 0 ELSE 1 END, "
                "CASE WHEN archived_at IS NULL THEN 0 ELSE 1 END, created_at, name",
                (include_archived,),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, created_at, dashboard_layout, archived_at FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return self._decode(row) if row else None

    def create_project(self, name: str) -> dict[str, Any]:
        clean_name = " ".join(name.split())
        if not clean_name or len(clean_name) > 80:
            raise ValueError("Project name must contain 1 to 80 characters")
        slug = re.sub(r"[^a-z0-9]+", "-", clean_name.casefold()).strip("-")[:36] or "project"
        project_id = f"{slug}-{uuid.uuid4().hex[:8]}"
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO projects (id, name, dashboard_layout) VALUES (?, ?, ?)",
                (project_id, clean_name, json.dumps(DEFAULT_LAYOUT)),
            )
        project = self.get_project(project_id)
        assert project is not None
        return project

    def save_layout(self, project_id: str, layout: dict[str, Any]) -> dict[str, Any] | None:
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE projects SET dashboard_layout = ? WHERE id = ?",
                (json.dumps(layout), project_id),
            )
        return self.get_project(project_id) if result.rowcount else None

    def archive_project(self, project_id: str) -> dict[str, Any] | None:
        if project_id == "default":
            raise ValueError("The Default Project cannot be archived")
        archived_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE projects SET archived_at = ? WHERE id = ?",
                (archived_at, project_id),
            )
        return self.get_project(project_id) if result.rowcount else None

    def restore_project(self, project_id: str) -> dict[str, Any] | None:
        if project_id == "default":
            raise ValueError("The Default Project is always active")
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE projects SET archived_at = NULL WHERE id = ?",
                (project_id,),
            )
        return self.get_project(project_id) if result.rowcount else None

    def delete_project(self, project_id: str) -> bool:
        if project_id == "default":
            raise ValueError("The Default Project cannot be deleted")
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM project_links WHERE from_project_id = ? OR to_project_id = ?",
                (project_id, project_id),
            )
            result = connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return bool(result.rowcount)

    def create_project_link(
        self,
        *,
        from_project_id: str,
        from_entity_id: str,
        from_entity_name: str,
        to_project_id: str,
        to_entity_id: str,
        to_entity_name: str,
        link_kind: str,
        rationale: str,
    ) -> dict[str, Any]:
        link_id = f"plink-{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO project_links
                   (id, from_project_id, from_entity_id, from_entity_name, to_project_id,
                    to_entity_id, to_entity_name, link_kind, rationale)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (link_id, from_project_id, from_entity_id, from_entity_name, to_project_id,
                 to_entity_id, to_entity_name, link_kind, rationale),
            )
        return next(link for link in self.list_project_links(from_project_id) if link["id"] == link_id)

    def list_project_links(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT l.id, l.from_project_id, fp.name AS from_project_name,
                          l.from_entity_id, l.from_entity_name, l.to_project_id,
                          tp.name AS to_project_name, l.to_entity_id, l.to_entity_name,
                          l.link_kind, l.rationale, l.created_at
                   FROM project_links l
                   JOIN projects fp ON fp.id = l.from_project_id
                   JOIN projects tp ON tp.id = l.to_project_id
                   WHERE l.from_project_id = ? OR l.to_project_id = ?
                   ORDER BY l.created_at DESC, l.id""",
                (project_id, project_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_project_link(self, project_id: str, link_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                "DELETE FROM project_links WHERE id = ? AND (from_project_id = ? OR to_project_id = ?)",
                (link_id, project_id, project_id),
            )
        return bool(result.rowcount)


@dataclass
class ProjectRuntime:
    project_id: str
    kuzu: KuzuClient
    orchestrator: Orchestrator
    wiki_sync: WikiSync


class ProjectRuntimeManager:
    """Lazily opens one graph and vault set per project for the API process."""

    def __init__(self, store: ProjectStore):
        self.store = store
        self._runtimes: dict[str, ProjectRuntime] = {}
        self._lock = asyncio.Lock()

    async def get(self, project_id: str) -> ProjectRuntime:
        runtime = self._runtimes.get(project_id)
        if runtime is not None:
            return runtime
        async with self._lock:
            runtime = self._runtimes.get(project_id)
            if runtime is not None:
                return runtime
            project = self.store.get_project(project_id)
            if project is None:
                raise KeyError(project_id)

            if project_id == "default":
                db_path = settings.kuzu_db_path
                wiki_path = settings.wiki_vault_path
                raw_path = settings.raw_vault_path
                quarantine_path = settings.quarantine_path
            else:
                root = Path(settings.project_data_root) / project_id
                db_path = str(root / "kuzudb" / "graph.kuzu")
                wiki_path = str(root / "wiki")
                raw_path = str(root / "raw_vault")
                quarantine_path = str(root / "quarantine")

            kuzu = KuzuClient(db_path)
            await kuzu.connect()
            try:
                await ensure_schema(kuzu)
                wiki_sync = WikiSync(kuzu, wiki_path)
                orchestrator = Orchestrator(
                    kuzu,
                    wiki_vault_path=wiki_path,
                    raw_vault_path=raw_path,
                    quarantine_path=quarantine_path,
                )
            except Exception:
                await kuzu.close()
                raise

            runtime = ProjectRuntime(project_id, kuzu, orchestrator, wiki_sync)
            self._runtimes[project_id] = runtime
            return runtime

    async def delete_project(self, project_id: str) -> bool:
        """Close and remove one non-default project's graph, vaults, and registry row."""
        if project_id == "default":
            raise ValueError("The Default Project cannot be deleted")
        async with self._lock:
            runtime = self._runtimes.pop(project_id, None)
            if runtime is not None:
                await runtime.kuzu.close()
            project_root = Path(settings.project_data_root) / project_id
            if project_root.exists():
                await asyncio.to_thread(shutil.rmtree, project_root)
            return self.store.delete_project(project_id)

    async def close(self) -> None:
        runtimes = list(self._runtimes.values())
        self._runtimes.clear()
        await asyncio.gather(*(runtime.kuzu.close() for runtime in runtimes), return_exceptions=True)
