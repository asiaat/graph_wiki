"""Request-scoped active project selection."""

from __future__ import annotations

from contextvars import ContextVar

from fastapi import Request

_current_project_id: ContextVar[str] = ContextVar("current_project_id", default="default")


def set_current_project(project_id: str):
    return _current_project_id.set(project_id)


def reset_current_project(token) -> None:
    _current_project_id.reset(token)


def current_project_id() -> str:
    return _current_project_id.get()


async def get_current_runtime(request: Request | None = None):
    if request is not None:
        manager = request.app.state.project_manager
    else:
        from kuzuwiki.main import app

        manager = app.state.project_manager
    return await manager.get(current_project_id())
