"""API Routes: Document/URL ingestion pipeline."""

import logging
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.jev.schemas import RawDocumentPayload
from app.agents.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


class IngestResponse(BaseModel):
    accepted: bool
    doc_sha256: str | None = None
    error: str | None = None
    compile_stats: dict[str, int] | None = None


async def get_orchestrator() -> Orchestrator:
    from app.main import app

    return app.state.orchestrator


@router.post("/document", response_model=IngestResponse)
async def ingest_document(
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
    title: str | None = Form(None),
    domain: str | None = Form(None),
):
    """Upload PDF/DOCX/URL/Archive; runs Gatekeeper → HVG → Swarm → Compiler."""
    if not file and not url:
        raise HTTPException(400, "Either file or url must be provided")

    content = None
    if file:
        content_bytes = await file.read()
        if file.content_type == "application/pdf":
            try:
                import pypdf
                import io

                reader = pypdf.PdfReader(io.BytesIO(content_bytes))
                content = "\n".join(page.extract_text() for page in reader.pages)
            except Exception as exc:
                raise HTTPException(400, f"PDF extraction failed: {exc}")
        elif (
            file.content_type
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ):
            try:
                import docx
                import io

                doc = docx.Document(io.BytesIO(content_bytes))
                content = "\n".join(p.text for p in doc.paragraphs)
            except Exception as exc:
                raise HTTPException(400, f"DOCX extraction failed: {exc}")
        else:
            content = content_bytes.decode("utf-8", errors="ignore")
    elif url:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.text
        except Exception as exc:
            raise HTTPException(400, f"URL fetch failed: {exc}")

    if not content:
        raise HTTPException(400, "No extractable content")

    payload = RawDocumentPayload(
        content=content,
        uri=url,
        title=title,
        domain=domain,
    )

    orchestrator = await get_orchestrator()
    state = await orchestrator.ingest_and_compile(payload)

    return IngestResponse(
        accepted=state.get("error") is None,
        doc_sha256=state.get("gatekeeper_result", {}).get("doc_sha256"),
        error=state.get("error"),
        compile_stats=state.get("compile_stats"),
    )
