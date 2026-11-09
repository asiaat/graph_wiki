#!/usr/bin/env python3
"""Import the structured layer of an open-source corpus into the compiled graph.

The corpus already contains machine-extracted entities and relations
(``01_processed/entities.json`` and ``network.json``). Re-deriving them with
an LLM would be slower, less complete and would lose the attributes - so
they are imported directly, and the LLM pass is left to add the
verbatim-quoted *claim* layer on top.

Nothing is lost in translation: the corpus's own edge vocabulary is mapped
onto the JEV relation types, and the original type is stored verbatim on the
edge, so a mapping that is not one-to-one is still reversible.

Usage::

    python scripts/import_osint_corpus.py --corpus /root/proj/osint_berlin26
    python scripts/import_osint_corpus.py --corpus ... --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Optional

from kuzuwiki.db.kuzu_client import KuzuClient
from kuzuwiki.db.schema_init import ensure_schema
from kuzuwiki.db.wiki_sync import WikiSync
from kuzuwiki.jev.entity_resolver import entity_id
from kuzuwiki.jev.schemas import EntityCategory, RelationType, Sensitivity, default_sensitivity_for
from kuzuwiki.jev.tolerant_json import load_tolerant

logger = logging.getLogger("import_corpus")

# --------------------------------------------------------------------------
# Vocabulary mapping
# --------------------------------------------------------------------------

#: corpus category -> JEV entity category
CATEGORY_MAP: dict[str, EntityCategory] = {
    "people": EntityCategory.PERSON,
    "organizations": EntityCategory.ORGANIZATION,
    "companies": EntityCategory.ORGANIZATION,
    "authorities": EntityCategory.ORGANIZATION,
    "service_providers": EntityCategory.SERVICE_PROVIDER,
    "locations": EntityCategory.LOCATION,
    "phones": EntityCategory.PHONE_NUMBER,
    "emails": EntityCategory.EMAIL_ADDRESS,
    "urls": EntityCategory.WEBSITE,
    "websites_scanned": EntityCategory.WEBSITE,
    "channels": EntityCategory.TELEGRAM_CHANNEL,
    "telegram_channels_scanned": EntityCategory.TELEGRAM_CHANNEL,
    "job_types": EntityCategory.JOB_TYPE,
    "wages_observed": EntityCategory.JOB_TYPE,
    "techniques": EntityCategory.RISK_INDICATOR,
    "risk_indicators": EntityCategory.RISK_INDICATOR,
    "timeline_events": EntityCategory.EVENT,
    "events": EntityCategory.EVENT,
    "key_cases": EntityCategory.EVENT,
}

#: network node type prefix -> JEV entity category
NODE_TYPE_MAP: dict[str, EntityCategory] = {
    "person": EntityCategory.PERSON,
    "org": EntityCategory.ORGANIZATION,
    "company": EntityCategory.ORGANIZATION,
    "organization": EntityCategory.ORGANIZATION,
    "intelligence": EntityCategory.ORGANIZATION,
    "location": EntityCategory.LOCATION,
    "phone": EntityCategory.PHONE_NUMBER,
    "infrastructure": EntityCategory.INFRASTRUCTURE,
    "group": EntityCategory.GROUP,
    "political": EntityCategory.POLITICAL_PARTY,
    "platform": EntityCategory.WEBSITE,
    "product": EntityCategory.COMPONENT,
}

#: corpus edge type -> (JEV relation type, reverse the direction?)
#:
#: The corpus states edges as "<subject> <type> <object>" with the meaning
#: carried by the type, and some types are written from the object's point of
#: view ("subsidiary_of" means the *source* is the subsidiary).
RELATION_MAP: dict[str, tuple[RelationType, bool]] = {
    # ownership and control
    "beneficial_owner": (RelationType.OWNS_CONTROLS, False),
    "shareholder": (RelationType.OWNS_CONTROLS, False),
    "former_owner": (RelationType.OWNS_CONTROLS, False),
    "subsidiary": (RelationType.OWNS_CONTROLS, False),
    "subsidiary_of": (RelationType.OWNS_CONTROLS, True),
    "command": (RelationType.OWNS_CONTROLS, False),
    # roles and employment
    "affiliation": (RelationType.AFFILIATED_WITH, False),
    "affiliated": (RelationType.AFFILIATED_WITH, False),
    "associated_with": (RelationType.AFFILIATED_WITH, False),
    "business_relationship": (RelationType.AFFILIATED_WITH, False),
    "overlap": (RelationType.AFFILIATED_WITH, False),
    "support": (RelationType.AFFILIATED_WITH, False),
    "cofounder": (RelationType.AFFILIATED_WITH, False),
    "cofounder_cfo": (RelationType.AFFILIATED_WITH, False),
    "cofounder_producer": (RelationType.AFFILIATED_WITH, False),
    "ceo_founder": (RelationType.AFFILIATED_WITH, False),
    "ceo_of": (RelationType.AFFILIATED_WITH, False),
    "director_of": (RelationType.AFFILIATED_WITH, False),
    "employed_by": (RelationType.AFFILIATED_WITH, False),
    "founder": (RelationType.AFFILIATED_WITH, False),
    "founder_of": (RelationType.AFFILIATED_WITH, False),
    "founded_by": (RelationType.AFFILIATED_WITH, False),
    "former_director_of": (RelationType.AFFILIATED_WITH, False),
    "former_managing_director": (RelationType.AFFILIATED_WITH, False),
    "managing_director": (RelationType.AFFILIATED_WITH, False),
    "operated_by": (RelationType.AFFILIATED_WITH, True),
    "security_service": (RelationType.AFFILIATED_WITH, True),
    # money
    "funding": (RelationType.FUNDS, False),
    "investor": (RelationType.FUNDS, False),
    # supply and production
    "contract": (RelationType.SUPPLIES_COMPONENT, False),
    "developer": (RelationType.MANUFACTURES, False),
    "operates_through": (RelationType.SUPPLIES_COMPONENT, False),
    "payment_processor": (RelationType.SUPPLIES_COMPONENT, False),
    "upstream_provider": (RelationType.SUPPLIES_COMPONENT, False),
    # place
    "base": (RelationType.LOCATED_IN, False),
    "born_in": (RelationType.LOCATED_IN, False),
    "debtor_address": (RelationType.LOCATED_IN, False),
    "headquartered_in": (RelationType.LOCATED_IN, False),
    "hosted_in": (RelationType.LOCATED_IN, False),
    "located_at": (RelationType.LOCATED_IN, False),
    "located_in": (RelationType.LOCATED_IN, False),
    "operates_from": (RelationType.OPERATES_FROM, False),
    "regional_hub": (RelationType.OPERATES_FROM, False),
    "registered_address": (RelationType.LOCATED_IN, False),
    # activity
    "attacked": (RelationType.ATTACKED, False),
    "exploitation": (RelationType.ATTACKED, False),
    "false_flag": (RelationType.ATTACKED, False),
    "possible_false_flag": (RelationType.ATTACKED, False),
    "handler": (RelationType.COMMUNICATES_WITH, False),
    "recruitment": (RelationType.RECRUITS_FROM, False),
}

#: Edge types that describe the *analysis*, not the world: they record that a
#: search was run, not that a relation exists.
ANALYSIS_ONLY_EDGES = {"connection_searched"}

#: Attributes that are really identifiers rather than prose.
IDENTIFIER_KEYS = {"email", "emails", "phone", "phones", "company_number", "registration", "hrb"}

_PAREN_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")
_PREFIX_RE = re.compile(r"^(person|org|location|group|company|political|platform)\s+", re.I)


def clean_node_label(label: str) -> str:
    """Turn a network node label into a plausible entity name."""
    name = str(label or "").strip()
    if not name:
        return name
    # "Robert Bagratuni (Mundfish CEO)" -> "Robert Bagratuni"
    stripped = _PAREN_SUFFIX_RE.sub("", name).strip()
    if stripped:
        name = stripped
    # "person_robert_bagratuni" -> "Robert Bagratuni"
    if "_" in name and " " not in name:
        parts = name.split("_")
        if len(parts) > 1:
            name = " ".join(part.capitalize() for part in parts[1:])
    return name.strip()


def node_category(node_id: str, node_type: str) -> EntityCategory:
    """Category of a network node, from its type or its id prefix."""
    if node_type:
        mapped = NODE_TYPE_MAP.get(str(node_type).lower())
        if mapped:
            return mapped
    prefix = str(node_id).split("_", 1)[0].lower()
    return NODE_TYPE_MAP.get(prefix, EntityCategory.ORGANIZATION)


def summarise(record: dict[str, Any], category: EntityCategory) -> str:
    """Build a one-line factual summary from a corpus entity record."""
    attributes = record.get("attributes")
    if not isinstance(attributes, dict):
        attributes = {}

    bits: list[str] = []
    for key in ("title", "role", "organization", "company", "origin", "location", "type"):
        value = attributes.get(key)
        if isinstance(value, str) and value.strip() and value.strip() != "Unknown":
            bits.append(f"{key}: {value.strip()}")
        if len(bits) >= 3:
            break

    if bits:
        return "; ".join(bits) + "."

    name = str(record.get("name", "")).strip()
    return f"{category.value} named {name}." if name else f"{category.value}."


def deterministic_ids(record: dict[str, Any]) -> dict[str, str]:
    """Pull identifier-like attributes into the deterministic id map."""
    attributes = record.get("attributes")
    if not isinstance(attributes, dict):
        return {}
    found: dict[str, str] = {}
    for key, value in attributes.items():
        if key.lower() in IDENTIFIER_KEYS and isinstance(value, str) and value.strip():
            found[key.lower()] = value.strip()
    return found


class CorpusImporter:
    """Loads a corpus's structured layer into the compiled graph."""

    def __init__(self, client: KuzuClient, wiki_vault_path: str):
        self.kuzu = client
        self.wiki_sync = WikiSync(client, wiki_vault_path)
        self.entity_ids: dict[str, str] = {}
        self.stats = {
            "files": 0,
            "repaired_files": 0,
            "skipped_files": 0,
            "entities": 0,
            "new_entities": 0,
            "edges": 0,
            "unmapped_edge_types": 0,
        }
        self.unmapped_types: dict[str, int] = {}

    # ------------------------------------------------------------------ load

    def _load_json(self, path: Path) -> Optional[Any]:
        result = load_tolerant(str(path))
        if not result.ok:
            logger.error("Could not read %s: %s", path.name, result.error)
            self.stats["skipped_files"] += 1
            return None
        self.stats["files"] += 1
        if result.repaired:
            self.stats["repaired_files"] += 1
        return result.data

    def collect(self, corpus_root: Path) -> tuple[list[dict], list[dict]]:
        """Read every entities.json and network.json in the corpus."""
        entity_records: list[dict] = []
        edge_records: list[dict] = []

        for path in sorted(corpus_root.rglob("entities.json")):
            data = self._load_json(path)
            if data is None:
                continue
            for category, items in self._as_category_map(data).items():
                mapped = CATEGORY_MAP.get(category)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or item.get("label") or "").strip()
                    if not name:
                        continue
                    entity_records.append(
                        {
                            "name": name,
                            "category": mapped or EntityCategory.ORGANIZATION,
                            "corpus_category": category,
                            "aliases": [
                                str(a)
                                for a in (item.get("aliases") or [])
                                if isinstance(a, str) and a.strip()
                            ],
                            "attributes": item.get("attributes")
                            if isinstance(item.get("attributes"), dict)
                            else {},
                            "sources": [
                                str(s) for s in (item.get("sources") or []) if isinstance(s, str)
                            ],
                            "mentions": item.get("mentions"),
                            "first_seen": item.get("first_seen"),
                            "origin_file": path.name,
                        }
                    )

        for path in sorted(corpus_root.rglob("network.json")):
            data = self._load_json(path)
            if not data is None and isinstance(data, dict):
                nodes = data.get("nodes") or []
                edges = data.get("edges") or []
            elif isinstance(data, list):
                nodes, edges = [], data
            else:
                continue

            node_meta = {}
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node_id = str(node.get("id") or "")
                if not node_id:
                    continue
                node_meta[node_id] = {
                    "label": node.get("label") or node_id,
                    "type": node.get("type") or "",
                }

            for edge in edges:
                if not isinstance(edge, dict):
                    continue
                source = str(edge.get("source") or "")
                target = str(edge.get("target") or "")
                edge_type = str(edge.get("type") or "")
                if not source or not target or not edge_type:
                    continue
                edge_records.append(
                    {
                        "source": source,
                        "target": target,
                        "type": edge_type,
                        "weight": edge.get("weight"),
                        "nodes": node_meta,
                        "origin_file": path.name,
                    }
                )

        return entity_records, edge_records

    @staticmethod
    def _as_category_map(data: Any) -> dict[str, list]:
        """Normalise the two shapes the corpus uses into {category: [records]}."""
        if isinstance(data, list):
            return {"people": [d for d in data if isinstance(d, dict)]}
        if isinstance(data, dict):
            return {str(key): value for key, value in data.items() if isinstance(value, list)}
        return {}

    # --------------------------------------------------------------- writing

    async def write_entities(self, records: list[dict]) -> None:
        """Upsert every entity, merging duplicates across reports."""
        for record in records:
            name = record["name"]
            category = record["category"]
            eid = entity_id(category, name)

            existing = await self.kuzu.read(
                "MATCH (e:Entity {id: $id}) RETURN e.aliases AS aliases, "
                "e.summary AS summary, e.external_ids AS external_ids",
                {"id": eid},
            )
            aliases = list(record["aliases"])
            summary = summarise(record, category)
            ids = deterministic_ids(record)
            sources = record["sources"]

            if existing:
                self.stats["entities"] += 1
                prior_aliases = existing[0].get("aliases") or []
                merged = list(dict.fromkeys([*prior_aliases, *aliases]))
                await self.kuzu.write(
                    "MATCH (e:Entity {id: $id}) SET e.aliases = $aliases, "
                    "e.summary = $summary, e.external_ids = CAST($ids AS JSON)",
                    {
                        "id": eid,
                        "aliases": merged,
                        "summary": summary,
                        "ids": json.dumps(ids, sort_keys=True),
                    },
                )
                aliases = merged
            else:
                self.stats["entities"] += 1
                self.stats["new_entities"] += 1
                await self.kuzu.write(
                    """
                    MERGE (e:Entity {id: $id})
                    ON CREATE SET
                        e.canonical_name = $name,
                        e.category = $category,
                        e.aliases = $aliases,
                        e.external_ids = CAST($ids AS JSON),
                        e.summary = $summary,
                        e.wiki_markdown = '',
                        e.confidence_score = $confidence,
                        e.lifecycle_state = 'UNVERIFIED',
                        e.hvg_centrality = 0.0,
                        e.sensitivity = $sensitivity,
                        e.updated_at = $updated_at
                    """,
                    {
                        "id": eid,
                        "name": name,
                        "category": category.value,
                        "aliases": aliases,
                        "ids": json.dumps(ids, sort_keys=True),
                        "summary": summary,
                        "confidence": 0.5,
                        "sensitivity": default_sensitivity_for(category).value,
                        "updated_at": _now(),
                    },
                )

            self.entity_ids[name.lower()] = eid
            for alias in aliases:
                self.entity_ids.setdefault(alias.lower(), eid)

            # Provenance: which reports mention this entity.
            for source_ref in sources[:10]:
                await self._link_source(eid, source_ref)

    async def _link_source(self, eid: str, reference: str) -> None:
        """Link an entity to the SourceDoc it was extracted from, if ingested."""
        reference = reference.strip()
        if not reference:
            return
        rows = await self.kuzu.read(
            "MATCH (s:SourceDoc) WHERE s.title CONTAINS $needle "
            "OR s.raw_archive_path CONTAINS $needle RETURN s.sha256 AS sha256 LIMIT 1",
            {"needle": reference.split("/")[-1].replace(".md", "")},
        )
        if not rows:
            return
        await self.kuzu.write(
            """
            MATCH (e:Entity {id: $id})
            MATCH (s:SourceDoc {sha256: $sha256})
            MERGE (e)-[r:MENTIONED_IN]->(s)
            SET r.reference = $reference
            """,
            {"id": eid, "sha256": rows[0]["sha256"], "reference": reference},
        )

    async def write_edges(self, records: list[dict]) -> None:
        """Write the relation edges, keeping the corpus's original vocabulary."""
        for record in records:
            edge_type = record["type"]
            if edge_type in ANALYSIS_ONLY_EDGES:
                continue
            mapping = RELATION_MAP.get(edge_type)
            if mapping is None:
                self.stats["unmapped_edge_types"] += 1
                self.unmapped_types[edge_type] = self.unmapped_types.get(edge_type, 0) + 1
                continue
            relation_type, reverse = mapping

            source_id = await self._resolve_node(record["source"], record["nodes"])
            target_id = await self._resolve_node(record["target"], record["nodes"])
            if not source_id or not target_id or source_id == target_id:
                continue
            if reverse:
                source_id, target_id = target_id, source_id

            weight = record.get("weight")
            weight = float(weight) if isinstance(weight, (int, float)) else 0.6
            weight = min(1.0, weight / 10.0) if weight > 1 else weight

            await self.kuzu.write(
                """
                MATCH (a:Entity {id: $source})
                MATCH (b:Entity {id: $target})
                MERGE (a)-[r:RELATES_TO {relation_type: $relation_type}]->(b)
                SET r.original_type = $original_type,
                    r.weight = $weight,
                    r.is_disputed = $is_disputed
                """,
                {
                    "source": source_id,
                    "target": target_id,
                    "relation_type": relation_type.value,
                    "original_type": edge_type,
                    "weight": weight,
                    "is_disputed": edge_type in {"possible_false_flag", "false_flag"},
                },
            )
            self.stats["edges"] += 1

    async def _resolve_node(self, node_id: str, nodes: dict) -> Optional[str]:
        """Map a network node to an entity id, creating it when unknown."""
        meta = nodes.get(node_id) or {}
        label = clean_node_label(meta.get("label") or node_id)
        if not label:
            return None

        known = self.entity_ids.get(label.lower())
        if known:
            return known

        category = node_category(node_id, meta.get("type", ""))
        eid = entity_id(category, label)
        if eid not in self.entity_ids.values():
            await self.kuzu.write(
                """
                MERGE (e:Entity {id: $id})
                ON CREATE SET
                    e.canonical_name = $name,
                    e.category = $category,
                    e.aliases = [],
                    e.external_ids = CAST('{}' AS JSON),
                    e.summary = $summary,
                    e.wiki_markdown = '',
                    e.confidence_score = 0.5,
                    e.lifecycle_state = 'UNVERIFIED',
                    e.hvg_centrality = 0.0,
                    e.sensitivity = $sensitivity,
                    e.updated_at = $updated_at
                """,
                {
                    "id": eid,
                    "name": label,
                    "category": category.value,
                    "summary": f"{category.value} named {label}.",
                    "sensitivity": default_sensitivity_for(category).value,
                    "updated_at": _now(),
                },
            )
            self.stats["new_entities"] += 1
        self.entity_ids[label.lower()] = eid
        return eid

    async def run(self, corpus_root: Path, dry_run: bool = False) -> dict[str, Any]:
        entity_records, edge_records = self.collect(corpus_root)
        logger.info(
            "Corpus: %d entity record(s), %d edge record(s) from %s",
            len(entity_records),
            len(edge_records),
            corpus_root,
        )
        if dry_run:
            unmapped: dict[str, int] = {}
            for record in edge_records:
                if record["type"] not in RELATION_MAP and record["type"] not in ANALYSIS_ONLY_EDGES:
                    unmapped[record["type"]] = unmapped.get(record["type"], 0) + 1
            return {
                "entity_records": len(entity_records),
                "edge_records": len(edge_records),
                "unmapped_edge_types": unmapped,
            }

        await self.write_entities(entity_records)
        await self.write_edges(edge_records)
        await self.wiki_sync.sync_all_entities()
        return self.stats


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, help="path to the corpus root")
    parser.add_argument("--db", default="/data/kuzudb/graph.kuzu", help="KùzuDB path")
    parser.add_argument("--wiki", default="/data/wiki", help="wiki vault path")
    parser.add_argument("--dry-run", action="store_true", help="report and exit")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    client = await KuzuClient.init(args.db)
    try:
        await ensure_schema(client)
        importer = CorpusImporter(client, args.wiki)
        result = await importer.run(Path(args.corpus), dry_run=args.dry_run)
    finally:
        await client.close()
        KuzuClient._shared_instance = None

    print(json.dumps(result, indent=2, default=str))
    if importer.unmapped_types:
        print("\nUnmapped corpus edge types (stored nowhere - review these):")
        for edge_type, count in sorted(importer.unmapped_types.items(), key=lambda kv: -kv[1]):
            print(f"  {count:3d}  {edge_type}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
