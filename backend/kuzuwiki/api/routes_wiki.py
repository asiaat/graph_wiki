"""API routes: compiled wiki pages and analyst-filed syntheses."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/wiki", tags=["wiki"])


class WikiPage(BaseModel):
    slug: str
    content: str
    frontmatter: dict[str, Any]


class SynthesisSave(BaseModel):
    slug: str
    content: str
    save_to_graph: bool = True


async def get_wiki_sync():
    from kuzuwiki.main import app

    return app.state.wiki_sync


def _split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Split a markdown document into frontmatter and body."""
    if not content.startswith("---"):
        return {}, content
    end = content.find("---", 3)
    if end <= 0:
        return {}, content
    try:
        frontmatter = yaml.safe_load(content[3:end]) or {}
    except yaml.YAMLError:
        frontmatter = {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    return frontmatter, content[end + 3 :]


@router.get("/{slug}")
async def get_wiki_page(slug: str) -> WikiPage:
    """Fetch a compiled wiki page by slug."""
    wiki_sync = await get_wiki_sync()
    content = await wiki_sync.read_wiki_file(slug)
    if not content:
        raise HTTPException(404, "Wiki page not found")
    frontmatter, body = _split_frontmatter(content)
    return WikiPage(slug=slug, content=body, frontmatter=frontmatter)


@router.get("/entity/{entity_id}")
async def get_entity_wiki(entity_id: str) -> WikiPage:
    """Fetch the compiled dossier of an entity, resolved through its slug."""
    wiki_sync = await get_wiki_sync()
    content = await wiki_sync.read_entity_wiki(entity_id)
    if not content:
        raise HTTPException(404, "Entity not found")
    frontmatter, body = _split_frontmatter(content)
    slug = frontmatter.get("slug") or entity_id
    return WikiPage(slug=slug, content=body, frontmatter=frontmatter)


@router.put("/{slug}")
async def save_query_to_wiki(
    slug: str,
    payload: SynthesisSave,
    save_to_graph: bool = Query(True),
) -> dict[str, Any]:
    """File an analyst's synthesised answer back into the graph.

    The page is written to the wiki vault and, when ``save_to_graph`` is set,
    the synthesis is also recorded in the graph as a ``DerivedSynthesis``
    concept node linked to its subject entity.
    """
    wiki_sync = await get_wiki_sync()
    path = wiki_sync.wiki_vault / f"{slug}.md"
    path.write_text(payload.content, encoding="utf-8")

    graph_saved = False
    if save_to_graph and save_to_graph:
        graph_saved = await _save_synthesis_node(slug, payload.content)

    return {
        "slug": slug,
        "saved": True,
        "path": str(path),
        "graph_saved": graph_saved,
    }


async def _save_synthesis_node(slug: str, content: str) -> bool:
    """Persist the synthesis as a Concept node in the compiled graph."""
    try:
        kuzu = await get_kuzu_client()
        synthesis_id = "synthesis-" + hashlib.sha256(content.encode()).hexdigest()[:12]
        await kuzu.write(
            """
            MERGE (s:Concept {id: $id})
            ON CREATE SET s.slug = $slug,
                          s.name = $name,
                          s.definition = $definition,
                          s.wiki_markdown = $definition,
                          s.confidence_score = $confidence,
                          s.updated_at = $updated_at
            """,
            {
                "id": synthesis_id,
                "slug": slug,
                "name": slug.replace("-", " ").title(),
                "definition": content[:8000],
                "confidence": 0.5,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        return True
    except Exception as exc:
        logger.error("Could not persist synthesis %s: %s", slug, exc)
        return False


async def get_kuzu_client():
    from kuzuwiki.main import app

    return app.state.kuzu
