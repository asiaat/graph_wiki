#!/usr/bin/env python3
"""Browser smoke test for the workbench and its whole-wiki graph view.

Run against the local Compose frontend with ``python3 scripts/smoke_test.py``.
Set ``SMOKE_BASE_URL`` to test another deployment. Install the optional browser
dependency with ``pip install -e 'backend[smoke]'`` and install Chromium with
``python3 -m playwright install chromium`` when no system Chromium is present.
"""

from __future__ import annotations

import os
import shutil
import sys
from urllib.parse import urljoin


def main() -> int:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is missing. Install it with: pip install -e 'backend[smoke]'",
            file=sys.stderr,
        )
        return 2

    base_url = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
    chromium_path = os.getenv("SMOKE_CHROMIUM_EXECUTABLE") or next(
        (
            path
            for command in ("chromium", "chromium-browser", "google-chrome", "chrome")
            if (path := shutil.which(command))
        ),
        None,
    )
    browser_errors: list[str] = []

    try:
        with sync_playwright() as playwright:
            launch_options = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if chromium_path:
                launch_options["executable_path"] = chromium_path
            browser = playwright.chromium.launch(**launch_options)
            page = browser.new_page()
            page.on("pageerror", lambda error: browser_errors.append(str(error)))

            response = page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
            assert response is not None and response.status == 200, (
                f"Workbench returned HTTP {response.status if response else 'no response'}"
            )
            page.get_by_role("heading", name="Knowledge Workbench").wait_for(timeout=20_000)
            page.get_by_role("button", name="Switch to dark theme").click()
            page.wait_for_function("() => document.documentElement.classList.contains('dark')", timeout=5_000)
            page.reload(wait_until="domcontentloaded")
            page.get_by_role("heading", name="Knowledge Workbench").wait_for(timeout=20_000)
            page.wait_for_function("() => document.documentElement.classList.contains('dark')", timeout=5_000)
            page.get_by_role("button", name="Switch to light theme").click()
            page.wait_for_function("() => !document.documentElement.classList.contains('dark')", timeout=5_000)
            page.get_by_role("heading", name="Acme Corporation").wait_for(timeout=20_000)
            page.get_by_role("region", name="Add a source to this project").wait_for(timeout=10_000)
            page.get_by_role("button", name="Projects", exact=True).click()
            page.get_by_role("heading", name="Projects").wait_for(timeout=5_000)
            page.get_by_role("complementary", name="Workspace explorer").get_by_role("button", name="Default Project", exact=False).wait_for(timeout=5_000)
            page.get_by_role("button", name="Explorer", exact=True).click()
            file_input = page.locator('input[aria-label="Choose source files"]')
            assert file_input.get_attribute("multiple") is not None, (
                "Source uploader does not allow selecting multiple files"
            )
            upload_attempts = {"count": 0}

            def mock_partial_upload(route):
                upload_attempts["count"] += 1
                if upload_attempts["count"] == 2:
                    route.fulfill(status=503, json={"detail": "Simulated temporary failure"})
                else:
                    route.fulfill(status=200, json={
                        "accepted": True,
                        "quarantined": False,
                        "doc_sha256": "a" * 64,
                    })

            page.route("**/api/v1/ingest/document", mock_partial_upload)
            file_input.set_input_files({"name": "smoke-ok.txt", "mimeType": "text/plain", "buffer": b"A harmless smoke-test source document."})
            file_input.set_input_files({"name": "smoke-retry.txt", "mimeType": "text/plain", "buffer": b"A second harmless smoke-test source document."})
            selected_files = page.get_by_role("list", name="Selected files")
            selected_files.get_by_text("smoke-ok.txt").wait_for(timeout=5_000)
            selected_files.get_by_text("smoke-retry.txt").wait_for(timeout=5_000)
            page.get_by_role("button", name="Projects", exact=True).click()
            page.get_by_role("button", name="Explorer", exact=True).click()
            selected_files.get_by_text("smoke-ok.txt").wait_for(timeout=5_000)
            selected_files.get_by_text("smoke-retry.txt").wait_for(timeout=5_000)
            page.get_by_role("button", name="Import 2 files into project").click()
            page.get_by_role("status").get_by_text("1 imported, 1 failed", exact=False).wait_for(timeout=10_000)
            selected_files.get_by_text("smoke-retry.txt").wait_for(timeout=5_000)
            assert selected_files.get_by_text("smoke-ok.txt").count() == 0, "Successfully uploaded file remained in retry queue"
            page.get_by_role("button", name="Retry 1 file into project").click()
            page.get_by_role("status").get_by_text("1 imported", exact=False).wait_for(timeout=10_000)
            assert selected_files.count() == 0, "Successful retry did not clear the pending file"
            page.unroute("**/api/v1/ingest/document", mock_partial_upload)
            page.get_by_role("tab", name="From URL").click()
            page.get_by_role("textbox", name="Source URL").wait_for(timeout=5_000)
            page.get_by_role("button", name="Close sidebar to icons").click()
            page.get_by_role("button", name="Open workspace sidebar").wait_for(timeout=5_000)
            page.get_by_role("button", name="Open workspace sidebar").click()
            page.get_by_role("region", name="Add a source to this project").wait_for(timeout=5_000)

            documents_response = page.request.get(urljoin(base_url + "/", "api/v1/ingest/documents"))
            assert documents_response.status == 200, f"Source list returned HTTP {documents_response.status}"
            documents = documents_response.json()["documents"]
            assert documents, "Source Vault file tree is empty"
            source = documents[0]
            content_response = page.request.get(urljoin(base_url + "/", f"api/v1/ingest/documents/{source['sha256']}/content"))
            assert content_response.status == 200, f"Source text preview returned HTTP {content_response.status}"
            page.get_by_role("button", name="Sources", exact=True).click()
            source_button_name = source.get("title") or source.get("domain") or source["sha256"][:16]
            page.get_by_role("button", name=source_button_name, exact=True).click()
            page.get_by_role("tab", name=source_button_name).wait_for(timeout=5_000)
            page.get_by_text("Source Vault /", exact=False).wait_for(timeout=5_000)

            projects_response = page.request.get(urljoin(base_url + "/", "api/v1/projects"))
            assert projects_response.status == 200, f"Projects API returned HTTP {projects_response.status}"
            assert any(project["id"] == "default" for project in projects_response.json()["projects"]), (
                "Default project was not listed"
            )
            all_projects_response = page.request.get(
                urljoin(base_url + "/", "api/v1/projects"), params={"include_archived": "true"}
            )
            for old_smoke_project in all_projects_response.json()["projects"]:
                if old_smoke_project["name"] == "Smoke Project Lifecycle":
                    page.request.delete(urljoin(base_url + "/", f"api/v1/projects/{old_smoke_project['id']}"))
            temporary_project = page.request.post(
                urljoin(base_url + "/", "api/v1/projects"),
                data={"name": "Smoke Project Lifecycle"},
            )
            assert temporary_project.status == 201, f"Could not create temporary smoke project: {temporary_project.text()}"
            temporary_project_id = temporary_project.json()["id"]
            page.reload(wait_until="domcontentloaded")
            page.get_by_role("heading", name="Knowledge Workbench").wait_for(timeout=20_000)
            page.get_by_role("button", name="Projects", exact=True).click()
            page.get_by_role("button", name="Archive Smoke Project Lifecycle").click()
            page.get_by_role("button", name="Show archived", exact=False).click()
            page.get_by_role("button", name="Restore Smoke Project Lifecycle").wait_for(timeout=5_000)
            page.get_by_role("button", name="Restore Smoke Project Lifecycle").click()
            page.get_by_role("button", name="Hide archived", exact=False).wait_for(timeout=5_000)
            page.get_by_role("button", name="Delete Smoke Project Lifecycle").wait_for(timeout=5_000)
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="Delete Smoke Project Lifecycle").click()
            projects_after_delete = page.request.get(urljoin(base_url + "/", "api/v1/projects")).json()["projects"]
            assert temporary_project_id not in {project["id"] for project in projects_after_delete}, (
                "Deleted smoke project remained in the active project list"
            )
            page.get_by_role("tab", name="Dashboard", exact=True).click()
            page.get_by_role("heading", name="Default Project").wait_for(timeout=10_000)
            page.get_by_role("heading", name="Cross-project links").wait_for(timeout=5_000)
            page.get_by_role("button", name="Customize dashboard").click()
            page.get_by_role("combobox", name="Graph Overview width").select_option("wide")
            page.get_by_role("button", name="Cancel").click()
            page.get_by_role("tab", name="Wiki", exact=True).click()
            page.get_by_role("heading", name="Knowledge Workbench").wait_for(timeout=10_000)

            page.get_by_role("tab", name="InfoStream").click()
            page.get_by_role("button", name="Open Graph Growth Overview full screen").click()
            page.wait_for_function("() => document.fullscreenElement !== null", timeout=5_000)
            page.keyboard.press("Escape")
            page.wait_for_function("() => document.fullscreenElement === null", timeout=5_000)
            page.get_by_role("tab", name="JEV Verification").click()
            page.get_by_role("heading", name="JEV Verification Inspector").wait_for(timeout=10_000)
            page.get_by_role("button", name="Open Entities by Category full screen").click()
            page.wait_for_function("() => document.fullscreenElement !== null", timeout=5_000)
            page.keyboard.press("Escape")
            page.wait_for_function("() => document.fullscreenElement === null", timeout=5_000)

            graph_response = page.request.get(urljoin(base_url + "/", "api/v1/graph/wiki-map"))
            assert graph_response.status == 200, f"Wiki graph API returned HTTP {graph_response.status}"
            graph = graph_response.json()
            assert graph.get("entities"), "Wiki graph has no dossier nodes"
            assert graph.get("edges"), "Wiki graph has no relationship edges"

            page.get_by_role("tab", name="Wiki", exact=True).click()
            page.get_by_role("button", name="Wiki Graph").click()
            page.get_by_role("heading", name="Wiki graph").wait_for(timeout=10_000)
            page.get_by_text("How are nodes and relations defined?").click()
            page.get_by_text("one compiled entity dossier", exact=False).wait_for(timeout=5_000)
            assert page.locator("canvas").count() > 0, "Wiki graph canvas did not render"
            page.get_by_text("Relations in this view").wait_for(timeout=10_000)
            page.get_by_role("button", name="Enter full screen").click()
            page.wait_for_function("() => document.fullscreenElement !== null", timeout=5_000)
            page.keyboard.press("Escape")
            page.wait_for_function("() => document.fullscreenElement === null", timeout=5_000)
            page.get_by_role("button", name="Enter full screen").click()
            page.wait_for_function("() => document.fullscreenElement !== null", timeout=5_000)
            page.get_by_role("button", name="Exit full screen").click()
            page.wait_for_function("() => document.fullscreenElement === null", timeout=5_000)
            page.get_by_role("button", name="Read wiki dossier").click()
            page.get_by_role("heading", name="Acme Corporation").wait_for(timeout=10_000)
            page.get_by_role("button", name="Neighborhood").click()
            page.get_by_role("heading", name="Neighborhood around Acme Corporation").wait_for(timeout=10_000)
            page.get_by_text("How should I read this neighborhood?").click()
            page.get_by_text("up to two steps away", exact=False).wait_for(timeout=5_000)
            page.locator('a[href="/#attack-index"]').click()
            page.get_by_role("heading", name="Attack-Index overview").wait_for(timeout=10_000)
            page.get_by_text("What does the Attack Index mean?").click()
            page.get_by_text("capped burstiness proxy", exact=False).wait_for(timeout=5_000)
            assert page.locator(".recharts-responsive-container").count() >= 2, (
                "Attack-Index visual charts did not render"
            )
            page.get_by_role("link", name="Raw JSON").wait_for(timeout=5_000)

            browser.close()

    except (AssertionError, PlaywrightError) as error:
        print(f"SMOKE TEST FAILED: {error}", file=sys.stderr)
        if browser_errors:
            print("Browser errors:", *browser_errors, sep="\n- ", file=sys.stderr)
        return 1

    if browser_errors:
        print("SMOKE TEST FAILED: browser JavaScript errors:", *browser_errors, sep="\n- ", file=sys.stderr)
        return 1

    print(
        f"SMOKE TEST PASSED: {base_url} rendered the workbench, dossier, wiki graph, and "
        "Attack-Index charts; project create/archive/restore/delete, batch upload retry retention, persistent file selection, source previews, main-area tabs, and fullscreen controls work."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
