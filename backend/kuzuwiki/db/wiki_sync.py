"""Bidirectional sync between KùzuDB Entity nodes and the Markdown wiki vault.

The vault is the human-readable face of the graph: every entity has a
``{slug}.md`` dossier with YAML frontmatter and ``[[wikilink]]`` references to
its neighbours.

Slug rules (the source of a long-standing bug):

* the slug is **stored on the Entity node** (``Entity.slug``), so the graph is
  the single source of truth;
* files are written as ``{slug}.md`` and looked up the same way;
* the route ``/api/v1/wiki/entity/{id}`` resolves through the stored slug,
  never by re-deriving it from the id.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

import yaml

from kuzuwiki.db.kuzu_client import KuzuClient

logger = logging.getLogger(__name__)

ENTITY_COLUMNS = (
    "e.id AS id",
    "e.slug AS slug",
    "e.canonical_name AS canonical_name",
    "e.category AS category",
    "e.aliases AS aliases",
    "e.external_ids AS external_ids",
    "e.summary AS summary",
    "e.wiki_markdown AS wiki_markdown",
    "e.confidence_score AS confidence_score",
    "e.lifecycle_state AS lifecycle_state",
    "e.hvg_centrality AS hvg_centrality",
    "e.sensitivity AS sensitivity",
    "e.embedding AS embedding",
    "e.updated_at AS updated_at",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(canonical_name: str, kuzu_id: str) -> str:
    """Deterministic, human-readable, collision-resistant slug."""
    base = "".join(c.lower() if c.isalnum() else "-" for c in canonical_name.strip())
    base = "-".join(filter(None, base.split("-")))[:64].strip("-")
    if not base:
        base = "entity"
    return f"{base}-{kuzu_id[:8]}"


def _coerce_external_ids(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            return {}
    return {}


class WikiSync:
    """Synchronizes Entity.wiki_markdown with the wiki vault."""

    def __init__(self, kuzu: KuzuClient, wiki_vault_path: str):
        self.kuzu = kuzu
        self.wiki_vault = Path(wiki_vault_path)
        self.wiki_vault.mkdir(parents=True, exist_ok=True)
        #: canonical name (lower) -> slug, used to resolve bare [[wikilinks]]
        self.slug_cache: dict[str, str] = {}

    # ------------------------------------------------------------- rendering

    @staticmethod
    def _now_iso() -> str:
        return _utcnow().isoformat()

    def _build_frontmatter(self, entity: dict) -> str:
        fm = {
            "slug": entity.get("slug") or "",
            "kuzu_id": entity["id"],
            "entity_type": entity.get("category", ""),
            "confidence_score": entity.get("confidence_score", 0.5),
            "admiralty_rating": entity.get("admiralty_rating", "F_CANNOT_BE_JUDGED"),
            "sources": entity.get("sources", []),
            "last_compiled": self._now_iso(),
            "aliases": entity.get("aliases", []) or [],
            "deterministic_ids": entity.get("external_ids")
            or _coerce_external_ids(entity.get("external_ids")),
            "lifecycle_state": entity.get("lifecycle_state", "UNVERIFIED"),
        }
        return "---\n" + yaml.dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n"

    def _render_wikilinks(self, markdown: str, entity: dict | None = None) -> str:
        """Render ``[[Name]]`` references as resolvable ``[[slug|Name]]`` links.

        Bare ``[[Name]]`` links are looked up in the vault; unknown targets
        are left untouched so a human can still repair them by hand.
        """
        if not markdown:
            return markdown

        def _replace(match: re.Match) -> str:
            inner = match.group(1)
            if "|" in inner:
                return match.group(0)
            name = inner.strip()
            slug = self.slug_cache.get(name.lower())
            if slug:
                return f"[[{slug}|{name}]]"
            return match.group(0)

        return re.sub(r"\[\[([^\]]+)\]\]", _replace, markdown)

    def compile_entity_markdown(self, entity: dict) -> str:
        """Compile the full markdown dossier for an entity row."""
        fm = self._build_frontmatter(entity)
        body = entity.get("wiki_markdown") or ""
        if not body.strip():
            body = f"# {entity.get('canonical_name', 'Unknown')}\n"
            summary = entity.get("summary") or ""
            if summary:
                body += f"\n{summary}\n"
            aliases = entity.get("aliases") or []
            if aliases:
                body += "\n**Also known as:** " + ", ".join(aliases) + "\n"
        return fm + self._render_wikilinks(body)

    # --------------------------------------------------------------- writing

    async def write_wiki_file(self, entity: dict) -> Path:
        """Write (or rewrite) the compiled markdown file for an entity."""
        slug = entity.get("slug") or _slugify(entity.get("canonical_name", ""), entity["id"])
        entity["slug"] = slug
        filepath = self.wiki_vault / f"{slug}.md"
        markdown = self.compile_entity_markdown(entity)
        filepath.write_text(markdown, encoding="utf-8")
        logger.info("Wrote wiki file: %s", filepath)
        return filepath

    async def read_wiki_file(self, slug: str) -> str | None:
        filepath = self.wiki_vault / f"{slug}.md"
        if not filepath.exists():
            return None
        return filepath.read_text(encoding="utf-8")

    async def sync_all_entities(self) -> int:
        """Full reconciliation pass: KùzuDB -> wiki vault."""
        entities = await self.kuzu.read(f"MATCH (e:Entity) RETURN {', '.join(ENTITY_COLUMNS)}")
        self.slug_cache = {
            str(row.get("canonical_name", "")).lower(): str(row.get("slug") or "")
            for row in entities
        }
        count = 0
        for row in entities:
            entity = dict(row)
            entity["external_ids"] = _coerce_external_ids(entity.get("external_ids"))
            # Convert embedding from KùzuDB's list format to a plain list
            if "embedding" in entity and entity["embedding"] is not None:
                emb = entity["embedding"]
                if hasattr(emb, "tolist"):
                    entity["embedding"] = emb.tolist()
                elif hasattr(emb, "__iter__") and not isinstance(emb, str):
                    entity["embedding"] = list(emb)
            await self._attach_provenance(entity)
            document = await self._entity_document(entity)
            entity["wiki_markdown"] = document
            await self.write_wiki_file(entity)
            count += 1
        return count

    async def _attach_provenance(self, entity: dict) -> None:
        """Attach the source documents (and their Admiralty rating) to an entity.

        Without this the dossier frontmatter claimed ``F_CANNOT_BE_JUDGED``
        and an empty source list even when the claim was grounded in a
        perfectly graded article.
        """
        entity_id = entity.get("id")
        if not entity_id:
            return
        try:
            rows = await self.kuzu.read(
                """
                MATCH (c:Claim)-[:ASSERTS_ABOUT]->(e:Entity {id: $id})
                MATCH (c)-[:EVIDENCED_BY]->(s:SourceDoc)
                RETURN DISTINCT s.sha256 AS sha256, s.admiralty_reliability AS admiralty
                """,
                {"id": entity_id},
            )
        except Exception as exc:
            logger.warning("Could not load provenance for %s: %s", entity_id, exc)
            rows = []

        sources: list[str] = []
        admiralty = ""
        for row in rows:
            sha = row.get("sha256")
            if sha:
                sources.append(str(sha))
            rating = row.get("admiralty")
            if rating and not admiralty:
                admiralty = str(rating)

        entity["sources"] = sources
        if admiralty:
            entity["admiralty_rating"] = admiralty

    async def _entity_document(self, entity: dict) -> str:
        """Build the dossier body from the graph: summary, claims, relations."""
        entity_id = entity["id"]
        lines: list[str] = [f"# {entity.get('canonical_name', 'Unknown')}", ""]

        summary = entity.get("summary") or ""
        if summary:
            lines += [summary, ""]

        aliases = entity.get("aliases") or []
        if aliases:
            lines += ["**Also known as:** " + ", ".join(aliases), ""]

        try:
            claims = await self.kuzu.read(
                """
                MATCH (c:Claim)-[:ASSERTS_ABOUT]->(e:Entity {id: $id})
                OPTIONAL MATCH (c)-[ev:EVIDENCED_BY]->(s:SourceDoc)
                RETURN c.statement AS statement, c.nli_entailment AS nli_entailment,
                       c.swarm_votes AS swarm_votes, ev.exact_quote AS quote
                """,
                {"id": entity_id},
            )
        except Exception as exc:
            logger.warning("Could not load claims for %s: %s", entity_id, exc)
            claims = []

        if claims:
            lines += ["## Claims", ""]
            for claim in claims:
                score = claim.get("nli_entailment")
                score_text = f" (entailment {score:.2f})" if isinstance(score, (int, float)) else ""
                lines.append(f"- {claim.get('statement')}{score_text}")
                quote = claim.get("quote")
                if quote:
                    lines.append(f"  > {quote}")
            lines.append("")

        try:
            relations = await self.kuzu.read(
                """
                MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
                WHERE a.id = $id OR b.id = $id
                OPTIONAL MATCH (c:Claim {claim_id: r.claim_id})
                OPTIONAL MATCH (c)-[ev:EVIDENCED_BY]->(s:SourceDoc)
                RETURN a.id AS source_id, a.canonical_name AS source,
                       a.slug AS source_slug, b.id AS target_id,
                       b.canonical_name AS target, b.slug AS target_slug,
                       r.relation_type AS relation_type, r.weight AS weight,
                       r.is_disputed AS is_disputed, r.claim_id AS claim_id,
                       c.statement AS claim_statement,
                       ev.exact_quote AS quote, s.sha256 AS source_sha256
                """,
                {"id": entity_id},
            )
        except Exception as exc:
            logger.warning("Could not load relations for %s: %s", entity_id, exc)
            relations = []

        try:
            contradiction_rows = await self.kuzu.read(
                "MATCH (a:Claim)-[:CONTRADICTS]->(b:Claim) "
                "RETURN a.claim_id AS claim_a, b.claim_id AS claim_b"
            )
            contradicted_claim_ids = {
                claim_id
                for row in contradiction_rows
                for claim_id in (row.get("claim_a"), row.get("claim_b"))
                if claim_id
            }
        except Exception as exc:
            logger.warning("Could not load contradiction links for %s: %s", entity_id, exc)
            contradicted_claim_ids = set()

        deduplicated_relations: dict[tuple[str, str, str], dict] = {}
        for relation in relations:
            key = (
                str(relation.get("source_id", "")),
                str(relation.get("target_id", "")),
                str(relation.get("relation_type", "")),
            )
            entry = deduplicated_relations.setdefault(
                key,
                {**relation, "evidence": []},
            )
            if relation.get("quote") and relation.get("source_sha256"):
                evidence = {
                    "quote": relation["quote"],
                    "source_sha256": relation["source_sha256"],
                }
                if evidence not in entry["evidence"]:
                    entry["evidence"].append(evidence)
        relations = list(deduplicated_relations.values())

        if relations:
            lines += ["## Relations", ""]
            for rel in relations:
                source = rel.get("source", "")
                target = rel.get("target", "")
                source_slug = rel.get("source_slug")
                target_slug = rel.get("target_slug")
                source_link = f"[[{source_slug}|{source}]]" if source_slug else source
                target_link = f"[[{target_slug}|{target}]]" if target_slug else target
                weight = rel.get("weight")
                weight_text = f" (weight {float(weight):.2f})" if weight is not None else ""
                is_disputed = rel.get("is_disputed") or rel.get("claim_id") in contradicted_claim_ids
                disputed_text = " — disputed" if is_disputed else ""
                lines.append(
                    f"- {source_link} — **{rel.get('relation_type')}** → "
                    f"{target_link}{weight_text}{disputed_text}"
                )
                expected_statement = f"{source} {rel.get('relation_type')} {target}"
                if rel.get("claim_statement") and rel.get("claim_statement") != expected_statement:
                    lines.append(f"  Claim: {rel['claim_statement']}")
                for evidence in rel["evidence"]:
                    lines.append(f"  > {evidence['quote']}")
                    lines.append(f"  Source SHA-256: `{evidence['source_sha256']}`")
            lines.append("")

        return "\n".join(lines)

    # -------------------------------------------------------------- mutation

    async def upsert_entity(self, entity_data: dict) -> str:
        """Upsert an Entity in KùzuDB and mirror it into the wiki vault."""
        entity = dict(entity_data)
        slug = entity.get("slug") or _slugify(entity["canonical_name"], entity["id"])
        entity["slug"] = slug
        entity.setdefault("wiki_markdown", "")
        entity.setdefault("aliases", [])
        entity.setdefault("external_ids", {})
        entity.setdefault("embedding", None)
        entity["external_ids_json"] = json.dumps(entity["external_ids"], sort_keys=True)
        entity["updated_at"] = _utcnow()

        # Prepare embedding - KùzuDB HNSW index requires non-null values.
        # Always provide a list; zero-vectors default to [0.0]*1024.
        embedding = entity.get("embedding")
        if embedding is None:
            embedding = [0.0] * 1024
        elif isinstance(embedding, list):
            if len(embedding) < 1024:
                embedding = embedding + [0.0] * (1024 - len(embedding))
            elif len(embedding) > 1024:
                embedding = embedding[:1024]
        else:
            embedding = [0.0] * 1024

        await self.kuzu.write(
            """
            MERGE (e:Entity {id: $id})
            ON CREATE SET
                e.slug = $slug,
                e.canonical_name = $canonical_name,
                e.category = $category,
                e.aliases = $aliases,
                e.external_ids = CAST($external_ids_json AS JSON),
                e.summary = $summary,
                e.wiki_markdown = $wiki_markdown,
                e.confidence_score = $confidence_score,
                e.lifecycle_state = $lifecycle_state,
                e.hvg_centrality = $hvg_centrality,
                e.sensitivity = $sensitivity,
                e.updated_at = $updated_at
            ON MATCH SET
                e.slug = $slug,
                e.canonical_name = $canonical_name,
                e.category = $category,
                e.aliases = $aliases,
                e.external_ids = CAST($external_ids_json AS JSON),
                e.summary = $summary,
                e.wiki_markdown = $wiki_markdown,
                e.confidence_score = $confidence_score,
                e.lifecycle_state = $lifecycle_state,
                e.hvg_centrality = $hvg_centrality,
                e.sensitivity = $sensitivity,
                e.updated_at = $updated_at
            """,
            {
                "id": entity["id"],
                "slug": entity["slug"],
                "canonical_name": entity["canonical_name"],
                "category": entity.get("category", "Organization"),
                "aliases": entity.get("aliases", []),
                "external_ids_json": entity["external_ids_json"],
                "summary": entity.get("summary", ""),
                "wiki_markdown": entity.get("wiki_markdown", ""),
                "confidence_score": entity.get("confidence_score", 0.5),
                "lifecycle_state": entity.get("lifecycle_state", "UNVERIFIED"),
                "hvg_centrality": entity.get("hvg_centrality", 0.0),
                "sensitivity": entity.get("sensitivity", "public"),
                "updated_at": entity["updated_at"],
            },
        )
        await self.write_wiki_file(entity)
        return slug

    # ---------------------------------------------------------------- reads

    async def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Fetch an entity row by id."""
        rows = await self.kuzu.read(
            f"MATCH (e:Entity {{id: $id}}) RETURN {', '.join(ENTITY_COLUMNS)}",
            {"id": entity_id},
        )
        if not rows:
            return None
        entity = dict(rows[0])
        entity["external_ids"] = _coerce_external_ids(entity.get("external_ids"))
        return entity

    async def get_entity_with_wiki(self, entity_id: str) -> dict[str, Any] | None:
        """Fetch an entity together with its compiled dossier."""
        entity = await self.get_entity(entity_id)
        if entity:
            return entity
        # Fallback: locate the file by its frontmatter kuzu_id.
        for md_file in sorted(self.wiki_vault.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            if not content.startswith("---"):
                continue
            fm_end = content.find("---", 3)
            if fm_end <= 0:
                continue
            try:
                fm = yaml.safe_load(content[3:fm_end]) or {}
            except yaml.YAMLError:
                continue
            if fm.get("kuzu_id") == entity_id:
                return {
                    "id": entity_id,
                    "slug": fm.get("slug", md_file.stem),
                    "canonical_name": fm.get("slug", md_file.stem),
                    "category": fm.get("entity_type", ""),
                    "aliases": fm.get("aliases", []),
                    "external_ids": fm.get("deterministic_ids", {}),
                    "summary": "",
                    "wiki_markdown": content,
                    "confidence_score": fm.get("confidence_score", 0.5),
                    "lifecycle_state": fm.get("lifecycle_state", "UNVERIFIED"),
                    "hvg_centrality": 0.0,
                    "updated_at": None,
                }
        return None

    async def read_entity_wiki(self, entity_id: str) -> str | None:
        """Return the compiled markdown for an entity, resolving via its slug."""
        entity = await self.get_entity(entity_id)
        if entity:
            slug = entity.get("slug") or _slugify(entity.get("canonical_name", ""), entity_id)
            content = await self.read_wiki_file(slug)
            if content:
                return content
            # The dossier may not have been compiled yet - compile it now.
            await self._attach_provenance(entity)
            document = await self._entity_document(entity)
            entity["wiki_markdown"] = document
            await self.write_wiki_file(entity)
            return self.compile_entity_markdown(entity)
        return None
