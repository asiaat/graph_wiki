"""API routes: document / URL ingestion through the compile pipeline."""

from __future__ import annotations

import io
import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from kuzuwiki.agents.orchestrator import Orchestrator
from kuzuwiki.jev.schemas import RawDocumentPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

#: Refuse absurdly large uploads - the raw vault is not a file store.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class IngestResponse(BaseModel):
    accepted: bool
    doc_sha256: str | None = None
    error: str | None = None
    compile_stats: dict[str, int] | None = None
    quarantined: bool = False


async def get_orchestrator() -> Orchestrator:
    from kuzuwiki.main import app

    return app.state.orchestrator


def _derive_domain(url: str | None) -> str | None:
    """Derive the publisher domain from the source URL."""
    if not url:
        return None
    host = urlparse(url).hostname
    return host or None


def _assert_public_url(url: str) -> None:
    """Reject URLs that point at private infrastructure (SSRF guard)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "Only http and https URLs are supported")
    host = parsed.hostname
    if not host:
        raise HTTPException(400, "URL has no hostname")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise HTTPException(400, f"Could not resolve host: {exc}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
        ):
            raise HTTPException(400, "Refusing to fetch a private or loopback address")


def _extract_text(content_bytes: bytes, content_type: str | None) -> str:
    """Extract plain text from a PDF, DOCX, HTML or plain-text upload."""
    if content_type == "application/pdf":
        try:
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(content_bytes))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise HTTPException(400, f"PDF extraction failed: {exc}") from exc

    if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        try:
            import docx

            document = docx.Document(io.BytesIO(content_bytes))
            return "\n".join(p.text for p in document.paragraphs)
        except Exception as exc:
            raise HTTPException(400, f"DOCX extraction failed: {exc}") from exc

    text = content_bytes.decode("utf-8", errors="ignore")
    if content_type in ("text/html", "application/xhtml+xml") or text.lstrip().lower().startswith(
        ("<!doctype html", "<html")
    ):
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(text, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            return soup.get_text("\n")
        except Exception as exc:
            logger.warning("HTML parsing failed, using raw text: %s", exc)
    return text


@router.get("/documents")
async def list_documents(limit: int = 50) -> dict[str, Any]:
    """List ingested source documents - the immutable vault index."""
    from kuzuwiki.main import app

    kuzu = app.state.kuzu
    rows = await kuzu.read(
        "MATCH (s:SourceDoc) "
        "RETURN s.sha256 AS sha256, s.title AS title, s.domain AS domain, "
        "s.published_at AS published_at, s.admiralty_reliability AS admiralty, "
        "s.slop_score AS slop_score, s.is_quarantined AS is_quarantined "
        "ORDER BY s.ingested_at DESC LIMIT $limit",
        {"limit": limit},
    )
    documents = []
    for row in rows:
        document = dict(row)
        for field in ("published_at",):
            value = document.get(field)
            if value is not None and hasattr(value, "isoformat"):
                document[field] = value.isoformat()
        documents.append(document)
    return {"documents": documents, "count": len(documents)}


@router.post("/document", response_model=IngestResponse)
async def ingest_document(
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
    title: str | None = Form(None),
    domain: str | None = Form(None),
    published_at: str | None = Form(None),
    domain_mode: str | None = Form(None),
) -> dict[str, Any]:
    """Upload a document or fetch a URL; runs Gatekeeper -> HVG -> Swarm -> Compiler."""
    if not file and not url:
        raise HTTPException(400, "Either file or url must be provided")

    content: str | None = None
    if file is not None:
        content_bytes = await file.read()
        if len(content_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Upload exceeds the 25 MB limit")
        content = _extract_text(content_bytes, file.content_type)
    elif url:
        _assert_public_url(url)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.text
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, f"URL fetch failed: {exc}") from exc

    if not content or not content.strip():
        raise HTTPException(400, "No extractable content")

    payload = RawDocumentPayload(
        content=content,
        uri=url,
        title=title,
        domain=domain or _derive_domain(url),
        published_at=published_at,
        domain_mode=domain_mode,
    )

    orchestrator = await get_orchestrator()
    state = await orchestrator.ingest_and_compile(payload)

    gatekeeper_result = state.get("gatekeeper_result")
    doc_sha256 = getattr(gatekeeper_result, "doc_sha256", None)
    quarantined = bool(getattr(gatekeeper_result, "quarantined", False))

    return {
        "accepted": state.get("error") is None,
        "doc_sha256": doc_sha256,
        "error": state.get("error"),
        "compile_stats": state.get("compile_stats"),
        "quarantined": quarantined,
    }
