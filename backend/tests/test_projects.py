"""Durable project metadata and saved dashboard layout tests."""

import pytest

from kuzuwiki.projects import DEFAULT_LAYOUT, ProjectStore


def test_project_store_persists_projects_and_layout(tmp_path):
    store_path = tmp_path / "projects.sqlite3"
    store = ProjectStore(store_path)
    created = store.create_project("  Acme investigation  ")
    assert created["name"] == "Acme investigation"
    assert created["id"].startswith("acme-investigation-")
    assert created["dashboard_layout"] == DEFAULT_LAYOUT

    layout = {"version": 1, "panels": [{"id": "attack-index", "width": "wide"}]}
    assert store.save_layout(created["id"], layout)["dashboard_layout"] == layout

    restarted = ProjectStore(store_path)
    projects = restarted.list_projects()
    assert [project["id"] for project in projects] == ["default", created["id"]]
    assert restarted.get_project(created["id"])["dashboard_layout"] == layout


def test_project_store_rejects_blank_name(tmp_path):
    store = ProjectStore(tmp_path / "projects.sqlite3")
    try:
        store.create_project("   ")
    except ValueError as error:
        assert "Project name" in str(error)
    else:
        raise AssertionError("blank project names must be rejected")


def test_cross_project_references_are_visible_from_both_projects_and_removable(tmp_path):
    store = ProjectStore(tmp_path / "projects.sqlite3")
    left = store.create_project("Left workspace")
    right = store.create_project("Right workspace")
    link = store.create_project_link(
        from_project_id=left["id"],
        from_entity_id="entity-left",
        from_entity_name="Entity in left",
        to_project_id=right["id"],
        to_entity_id="entity-right",
        to_entity_name="Entity in right",
        link_kind="possible_match",
        rationale="Compare identifiers before making a claim.",
    )

    assert link["from_entity_name"] == "Entity in left"
    assert link["to_entity_name"] == "Entity in right"
    assert store.list_project_links(left["id"])[0]["id"] == link["id"]
    assert store.list_project_links(right["id"])[0]["id"] == link["id"]
    assert store.delete_project_link(right["id"], link["id"])
    assert store.list_project_links(left["id"]) == []


def test_empty_project_can_be_archived_restored_and_deleted(tmp_path):
    store = ProjectStore(tmp_path / "projects.sqlite3")
    project = store.create_project("Empty workspace")
    project_id = project["id"]

    archived = store.archive_project(project_id)
    assert archived["archived_at"]
    assert project_id not in {item["id"] for item in store.list_projects()}
    assert project_id in {item["id"] for item in store.list_projects(include_archived=True)}

    restored = store.restore_project(project_id)
    assert restored["archived_at"] is None
    assert project_id in {item["id"] for item in store.list_projects()}
    assert store.delete_project(project_id)
    assert store.get_project(project_id) is None


def test_default_project_cannot_be_archived_or_deleted(tmp_path):
    store = ProjectStore(tmp_path / "projects.sqlite3")
    with pytest.raises(ValueError):
        store.archive_project("default")
    with pytest.raises(ValueError):
        store.delete_project("default")
