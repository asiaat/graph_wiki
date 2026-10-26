"""Backend FastAPI entry point with KùzuDB connection lifecycle management."""

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.kuzu_client import KuzuClient
from app.api.routes_ingest import router as ingest_router
from app.api.routes_graph import router as graph_router
from app.api.routes_wiki import router as wiki_router
from app.api.routes_osint import router as osint_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.kuzu = await KuzuClient.init(settings.kuzu_db_path)
    logger.info("KùzuDB connection established")
    yield
    await app.state.kuzu.close()
    logger.info("KùzuDB connection closed")


app = FastAPI(
    title="KuzuWiki-OSINT API",
    description="Graph-Compiled Expert Intelligence & Anti-Slop Knowledge System",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router, prefix="/api/v1/ingest", tags=["ingest"])
app.include_router(graph_router, prefix="/api/v1/graph", tags=["graph"])
app.include_router(wiki_router, prefix="/api/v1/wiki", tags=["wiki"])
app.include_router(osint_router, prefix="/api/v1/osint", tags=["osint"])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
