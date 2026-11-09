"""Project selection and dashboard layout API."""

from __future__ import annotations

import sqlite3
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])
PanelId = Literal[
    "graph-overview",
    "attack-index",
    "entity-categories",
    "source-reliability",
    "claim-confidence",
]


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


class DashboardPanel(BaseModel):
    id: PanelId
    width: Literal["half", "wide"] = "half"


class DashboardLayout(BaseModel):
    version: Literal[1] = 1
    panels: list[DashboardPanel] = Field(default_factory=list, max_length=5)

    @field_validator("panels")
    @classmethod
    def unique_panel_ids(cls, panels: list[DashboardPanel]) -> list[DashboardPanel]:
        ids = [panel.id for panel in panels]
        if len(ids) != len(set(ids)):
            raise ValueError("Dashboard panels must be unique")
        return panels


class ProjectLinkCreate(BaseModel):
    source_entity_id: str = Field(..., min_length=1, max_length=200)
    target_project_id: str = Field(..., min_length=1, max_length=100)
    target_entity_id: str = Field(..., min_length=1, max_length=200)
    link_kind: Literal["reference", "possible_match", "related_context", "source_overlap"]
    rationale: str = Field(default="", max_length=1200)


def _public_project(project: dict) -> dict:
    return {
        "id": project["id"],
        "name": project["name"],
        "created_at": project["created_at"],
        "archived_at": project.get("archived_at"),
        "dashboard_layout": project["dashboard_layout"],
    }


@router.get("")
async def list_projects(include_archived: bool = False) -> dict:
    from kuzuwiki.main import app

    return {"projects": [_public_project(project) for project in app.state.project_store.list_projects(include_archived)]}


@router.post("", status_code=201)
async def create_project(payload: ProjectCreate) -> dict:
    from kuzuwiki.main import app

    try:
        project = app.state.project_store.create_project(payload.name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _public_project(project)


@router.post("/{project_id}/archive")
async def archive_project(project_id: str) -> dict:
    from kuzuwiki.main import app

    try:
        project = app.state.project_store.archive_project(project_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if project is None:
        raise HTTPException(404, "Project not found")
    return _public_project(project)


@router.post("/{project_id}/restore")
async def restore_project(project_id: str) -> dict:
    from kuzuwiki.main import app

    try:
        project = app.state.project_store.restore_project(project_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if project is None:
        raise HTTPException(404, "Project not found")
    return _public_project(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str) -> None:
    from kuzuwiki.main import app

    if app.state.project_store.get_project(project_id) is None:
        raise HTTPException(404, "Project not found")
    try:
        await app.state.project_manager.delete_project(project_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/{project_id}/dashboard")
async def save_dashboard(project_id: str, layout: DashboardLayout) -> dict:
    from kuzuwiki.main import app

    if app.state.project_store.get_project(project_id) is None:
        raise HTTPException(404, "Project not found")
    saved = app.state.project_store.save_layout(project_id, layout.model_dump())
    if saved is None:
        raise HTTPException(404, "Project not found")
    return _public_project(saved)


@router.get("/{project_id}/entities")
async def list_project_entities(project_id: str, limit: int = Query(200, ge=1, le=500)) -> dict[str, Any]:
    from kuzuwiki.main import app

    if app.state.project_store.get_project(project_id) is None:
        raise HTTPException(404, "Project not found")
    runtime = await app.state.project_manager.get(project_id)
    rows = await runtime.kuzu.read(
        "MATCH (e:Entity) RETURN e.id AS id, e.canonical_name AS canonical_name, "
        "e.category AS category ORDER BY canonical_name LIMIT $limit",
        {"limit": limit},
    )
    return {"entities": rows}


@router.get("/{project_id}/links")
async def list_project_links(project_id: str) -> dict[str, Any]:
    from kuzuwiki.main import app

    if app.state.project_store.get_project(project_id) is None:
        raise HTTPException(404, "Project not found")
    return {"links": app.state.project_store.list_project_links(project_id)}


@router.post("/{project_id}/links", status_code=201)
async def create_project_link(project_id: str, payload: ProjectLinkCreate) -> dict[str, Any]:
    from kuzuwiki.main import app

    store = app.state.project_store
    if store.get_project(project_id) is None:
        raise HTTPException(404, "Project not found")
    if store.get_project(payload.target_project_id) is None:
        raise HTTPException(404, "Target project not found")
    if project_id == payload.target_project_id:
        raise HTTPException(422, "Choose a different project for a cross-project reference")

    source_runtime = await app.state.project_manager.get(project_id)
    source_rows = await source_runtime.kuzu.read(
        "MATCH (e:Entity {id: $id}) RETURN e.id AS id, e.canonical_name AS canonical_name",
        {"id": payload.source_entity_id},
    )
    target_runtime = await app.state.project_manager.get(payload.target_project_id)
    target_rows = await target_runtime.kuzu.read(
        "MATCH (e:Entity {id: $id}) RETURN e.id AS id, e.canonical_name AS canonical_name",
        {"id": payload.target_entity_id},
    )
    if not source_rows:
        raise HTTPException(404, "Source entity not found in this project")
    if not target_rows:
        raise HTTPException(404, "Target entity not found in the selected project")

    try:
        link = store.create_project_link(
            from_project_id=project_id,
            from_entity_id=payload.source_entity_id,
            from_entity_name=str(source_rows[0].get("canonical_name") or payload.source_entity_id),
            to_project_id=payload.target_project_id,
            to_entity_id=payload.target_entity_id,
            to_entity_name=str(target_rows[0].get("canonical_name") or payload.target_entity_id),
            link_kind=payload.link_kind,
            rationale=payload.rationale.strip(),
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "That cross-project reference already exists") from exc
    return {"link": link}


@router.delete("/{project_id}/links/{link_id}", status_code=204)
async def delete_project_link(project_id: str, link_id: str) -> None:
    from kuzuwiki.main import app

    if app.state.project_store.get_project(project_id) is None:
        raise HTTPException(404, "Project not found")
    if not app.state.project_store.delete_project_link(project_id, link_id):
        raise HTTPException(404, "Cross-project reference not found")
