"""Backend FastAPI entry point with KùzuDB connection lifecycle management."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from kuzuwiki.api.routes_graph import router as graph_router
from kuzuwiki.api.routes_ingest import router as ingest_router
from kuzuwiki.api.routes_osint import router as osint_router
from kuzuwiki.api.routes_projects import router as projects_router
from kuzuwiki.api.routes_query import router as query_router
from kuzuwiki.api.routes_stats import router as stats_router
from kuzuwiki.api.routes_wiki import router as wiki_router
from kuzuwiki.config import settings
from kuzuwiki.project_context import reset_current_project, set_current_project
from kuzuwiki.projects import ProjectRuntimeManager, ProjectStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = ProjectStore(f"{settings.project_data_root}/projects.sqlite3")
    manager = ProjectRuntimeManager(store)
    app.state.project_store = store
    app.state.project_manager = manager
    default_runtime = await manager.get("default")
    app.state.kuzu = default_runtime.kuzu
    app.state.wiki_sync = default_runtime.wiki_sync
    app.state.orchestrator = default_runtime.orchestrator
    logger.info("Default project graph, orchestrator, and wiki vault wired")

    # Warm the embedding client if available (non-blocking; logs warning if unavailable)
    try:
        from kuzuwiki.jev.embedding import get_embedding_client

        client = get_embedding_client()
        if client is not None:
            logger.info("Embedding model loaded: %s", client.model_name)
    except Exception as exc:
        logger.debug("Embedding model not available: %s", exc)

    try:
        yield
    finally:
        await manager.close()
        logger.info("Project KùzuDB connections closed")


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


@app.middleware("http")
async def select_project(request: Request, call_next):
    """Bind every API request to one known project before route execution."""
    if not request.url.path.startswith("/api/v1/"):
        return await call_next(request)
    project_id = (
        request.headers.get("x-project-id")
        or request.query_params.get("project_id")
        or "default"
    )
    store = getattr(request.app.state, "project_store", None)
    is_project_management = request.url.path.startswith("/api/v1/projects")
    if store is not None and not is_project_management and store.get_project(project_id) is None:
        return JSONResponse(status_code=404, content={"detail": "Project not found"})
    token = set_current_project(project_id)
    try:
        return await call_next(request)
    finally:
        reset_current_project(token)

# Router prefixes are declared on the routers themselves so that a route and
# its public path can never drift apart.
app.include_router(ingest_router)
app.include_router(graph_router)
app.include_router(query_router)
app.include_router(stats_router)
app.include_router(wiki_router)
app.include_router(osint_router)
app.include_router(projects_router)


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
