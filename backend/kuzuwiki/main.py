"""Backend FastAPI entry point with KùzuDB connection lifecycle management."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from kuzuwiki.agents.orchestrator import Orchestrator
from kuzuwiki.api.routes_graph import router as graph_router
from kuzuwiki.api.routes_ingest import router as ingest_router
from kuzuwiki.api.routes_osint import router as osint_router
from kuzuwiki.api.routes_wiki import router as wiki_router
from kuzuwiki.config import settings
from kuzuwiki.db.kuzu_client import KuzuClient
from kuzuwiki.db.schema_init import ensure_schema
from kuzuwiki.db.wiki_sync import WikiSync

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    kuzu = await KuzuClient.init(settings.kuzu_db_path)
    app.state.kuzu = kuzu
    logger.info("KùzuDB connection established")

    schema = await ensure_schema(kuzu)
    logger.info("KùzuDB schema ready: %s", schema)

    app.state.wiki_sync = WikiSync(kuzu, settings.wiki_vault_path)
    app.state.orchestrator = Orchestrator(
        kuzu,
        wiki_vault_path=settings.wiki_vault_path,
        raw_vault_path=settings.raw_vault_path,
        quarantine_path=settings.quarantine_path,
    )
    logger.info("Orchestrator and WikiSync wired")

    try:
        yield
    finally:
        await kuzu.close()
        logger.info("KùzuDB connection closed")


app = FastAPI(
    title="KuzuWiki-OSINT API",
    description="Graph-Compiled Expert Intelligence & Anti-Slop Knowledge System",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router prefixes are declared on the routers themselves so that a route and
# its public path can never drift apart.
app.include_router(ingest_router)
app.include_router(graph_router)
app.include_router(wiki_router)
app.include_router(osint_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": type(exc).__name__},
    )


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
