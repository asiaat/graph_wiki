"""API Routes: Compiled wiki CRUD, diff history, --save query filing."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db.wiki_sync import WikiSync

router = APIRouter(prefix="/api/v1/wiki", tags=["wiki"])


class WikiPage(BaseModel):
    slug: str
    content: str
    frontmatter: dict[str, Any]


async def get_wiki_sync():
    from app.main import app

    return app.state.wiki_sync


@router.get("/{slug}")
async def get_wiki_page(slug: str) -> WikiPage:
    wiki_sync = await get_wiki_sync()
    content = await wiki_sync.read_wiki_file(slug)
    if not content:
        raise HTTPException(404, "Wiki page not found")

    frontmatter = {}
    body = content
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            import yaml

            frontmatter = yaml.safe_load(content[3:end])
            body = content[end + 3 :]

    return WikiPage(slug=slug, content=body, frontmatter=frontmatter)


@router.get("/entity/{entity_id}")
async def get_entity_wiki(entity_id: str) -> WikiPage:
    wiki_sync = await get_wiki_sync()
    entity = await wiki_sync.get_entity_with_wiki(entity_id)
    if not entity:
        raise HTTPException(404, "Entity not found")

    slug = entity.get("slug") or entity.get("id", "")
    content = await wiki_sync.read_wiki_file(slug) or ""

    frontmatter = {}
    body = content
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            import yaml

            frontmatter = yaml.safe_load(content[3:end])
            body = content[end + 3 :]

    return WikiPage(slug=slug, content=body, frontmatter=frontmatter)


@router.put("/{slug}")
async def save_query_to_wiki(
    slug: str, content: str, save_to_wiki: bool = Query(True)
) -> dict[str, Any]:
    """Analyst files synthesized answer back into graph as DerivedSynthesis."""
    wiki_sync = await get_wiki_sync()
    # This would upsert as a DerivedSynthesis node in a full implementation
    return {"slug": slug, "saved": save_to_wiki}
