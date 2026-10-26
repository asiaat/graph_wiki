"""Bidirectional sync between KùzuDB Entity nodes and Markdown Wiki files."""

import asyncio
import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from app.db.kuzu_client import KuzuClient

logger = logging.getLogger(__name__)


class WikiSync:
    """Synchronizes Entity.wiki_markdown with /data/wiki/*.md files."""

    def __init__(self, kuzu: KuzuClient, wiki_vault_path: str):
        self.kuzu = kuzu
        self.wiki_vault = Path(wiki_vault_path)
        self.wiki_vault.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _slugify(canonical_name: str, kuzu_id: str) -> str:
        base = "".join(c.lower() if c.isalnum() else "-" for c in canonical_name.strip())
        base = "-".join(filter(None, base.split("-")))[:64]
        return f"{base}-{kuzu_id[:8]}"

    @staticmethod
    def _now_iso() -> str:
        return datetime.utcnow().isoformat() + "Z"

    def _build_frontmatter(self, entity: dict) -> str:
        fm = {
            "slug": entity["slug"],
            "kuzu_id": entity["id"],
            "entity_type": entity["category"],
            "confidence_score": entity.get("confidence_score", 0.5),
            "admiralty_rating": entity.get("admiralty_rating", "F_CANNOT_BE_JUDGED"),
            "sources": entity.get("sources", []),
            "last_compiled": self._now_iso(),
            "aliases": entity.get("aliases", []),
            "deterministic_ids": entity.get("deterministic_ids", {}),
        }
        return "---\n" + yaml.dump(fm, sort_keys=False) + "---\n\n"

    def _render_wikilinks(self, markdown: str) -> str:
        """Convert [[Entity]] to proper wiki links (placeholder)."""
        return markdown

    def compile_entity_markdown(self, entity: dict) -> str:
        """Recompiles full markdown dossier from KùzuDB Entity row."""
        fm = self._build_frontmatter(entity)
        body = (
            entity.get("wiki_markdown", "")
            or f"# {entity['canonical_name']}\n\nNo compiled content yet."
        )
        return fm + self._render_wikilinks(body)

    async def write_wiki_file(self, entity: dict) -> Path:
        """Writes/overwrites the compiled markdown file."""
        slug = entity.get("slug") or self._slugify(entity["canonical_name"], entity["id"])
        filepath = self.wiki_vault / f"{slug}.md"
        markdown = self.compile_entity_markdown(entity)
        filepath.write_text(markdown, encoding="utf-8")
        logger.info("Wrote wiki file: %s", filepath)
        return filepath

    async def read_wiki_file(self, slug: str) -> Optional[str]:
        filepath = self.wiki_vault / f"{slug}.md"
        if not filepath.exists():
            return None
        return filepath.read_text(encoding="utf-8")

    async def sync_all_entities(self) -> int:
        """Full reconciliation pass: KùzuDB → Wiki Vault."""
        entities = await self.kuzu.read(
            "MATCH (e:Entity) RETURN e.id, e.canonical_name, e.category, e.aliases, "
            "e.external_ids, e.summary, e.wiki_markdown, e.confidence_score, "
            "e.lifecycle_state, e.hvg_centrality, e.updated_at"
        )
        count = 0
        for row in entities:
            entity_dict = dict(
                zip(
                    [
                        "id",
                        "canonical_name",
                        "category",
                        "aliases",
                        "external_ids",
                        "summary",
                        "wiki_markdown",
                        "confidence_score",
                        "lifecycle_state",
                        "hvg_centrality",
                        "updated_at",
                    ],
                    row,
                )
            )
            await self.write_wiki_file(entity_dict)
            count += 1
        return count

    async def upsert_entity(self, entity_data: dict) -> str:
        """Upserts Entity in KùzuDB and syncs wiki file."""
        slug = self._slugify(entity_data["canonical_name"], entity_data["id"])
        entity_data["slug"] = slug
        entity_data["wiki_markdown"] = entity_data.get("wiki_markdown", "")
        entity_data["updated_at"] = self._now_iso()

        cypher = """
        MERGE (e:Entity {id: $id})
        ON CREATE SET
            e.canonical_name = $canonical_name,
            e.category = $category,
            e.aliases = $aliases,
            e.external_ids = $external_ids,
            e.summary = $summary,
            e.wiki_markdown = $wiki_markdown,
            e.confidence_score = $confidence_score,
            e.lifecycle_state = $lifecycle_state,
            e.hvg_centrality = $hvg_centrality,
            e.updated_at = $updated_at
        ON MATCH SET
            e.canonical_name = $canonical_name,
            e.category = $category,
            e.aliases = $aliases,
            e.external_ids = $external_ids,
            e.summary = $summary,
            e.wiki_markdown = $wiki_markdown,
            e.confidence_score = $confidence_score,
            e.lifecycle_state = $lifecycle_state,
            e.hvg_centrality = $hvg_centrality,
            e.updated_at = $updated_at
        """
        await self.kuzu.enqueue_write(cypher, entity_data)
        await self.write_wiki_file(entity_data)
        return slug

    async def get_entity_with_wiki(self, entity_id: str) -> Optional[dict]:
        """Fetches entity from KùzuDB, falls back to wiki file if needed."""
        rows = await self.kuzu.read("MATCH (e:Entity {id: $id}) RETURN e", {"id": entity_id})
        if rows:
            return dict(
                zip(
                    [
                        "id",
                        "canonical_name",
                        "category",
                        "aliases",
                        "external_ids",
                        "summary",
                        "wiki_markdown",
                        "confidence_score",
                        "lifecycle_state",
                        "hvg_centrality",
                        "updated_at",
                    ],
                    rows[0],
                )
            )
        # Fallback to wiki file
        for md_file in self.wiki_vault.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            if content.startswith("---"):
                fm_end = content.find("---", 3)
                if fm_end > 0:
                    fm = yaml.safe_load(content[3:fm_end])
                    if fm.get("kuzu_id") == entity_id:
                        return fm
        return None
