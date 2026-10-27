"""WP-7 gate: the dev stack configuration must be internally consistent.

These checks guard the infrastructure defects that made the stack impossible
to start: an invalid ``COPY`` redirect, ``npm ci`` without a lockfile, a
Docker image that baked the live API key into a layer, a compose file that
blanked the key through ``environment:`` precedence, and services pointed at
modules that do not exist.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("repo_root")


def _read(repo_root: Path, relative: str) -> str:
    path = repo_root / relative
    assert path.exists(), f"{relative} is missing"
    return path.read_text(encoding="utf-8")


def test_backend_dockerfile_copies_sources_before_install():
    """``pip install -e .`` fails when the package directory is absent."""
    dockerfile = _read(Path(__file__).resolve().parents[2], "backend/Dockerfile")
    install_at = dockerfile.find("pip install --no-cache-dir -e .")
    copy_at = dockerfile.find("COPY backend/kuzuwiki/")
    assert install_at != -1, "the editable install is missing"
    assert copy_at != -1, "the package sources are never copied"
    assert copy_at < install_at, "sources must be copied before the install"


def test_backend_dockerfile_does_not_mask_install_failures():
    """``pip install ... | tail -5`` returns tail's exit status, not pip's."""
    dockerfile = _read(Path(__file__).resolve().parents[2], "backend/Dockerfile")
    for line in dockerfile.splitlines():
        if "pip install" in line and "|" in line:
            pytest.fail(f"pip failure would be masked by a pipe: {line.strip()}")


def test_backend_dockerfile_never_bakes_the_env_file():
    dockerfile = _read(Path(__file__).resolve().parents[2], "backend/Dockerfile")
    assert "backend/.env" not in dockerfile, "the live .env must not be copied into the image"


def test_frontend_dockerfile_has_no_shell_redirect_in_copy():
    """``COPY x ./ 2>/dev/null || true`` is not valid Dockerfile syntax."""
    dockerfile = _read(Path(__file__).resolve().parents[2], "frontend/Dockerfile")
    for line in dockerfile.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("COPY"):
            assert "||" not in stripped and "2>" not in stripped, f"invalid COPY syntax: {stripped}"


def test_frontend_dockerfile_only_uses_npm_ci_with_a_lockfile():
    repo_root = Path(__file__).resolve().parents[2]
    dockerfile = (repo_root / "frontend/Dockerfile").read_text(encoding="utf-8")
    if "npm ci" in dockerfile:
        assert (repo_root / "frontend/package-lock.json").exists(), (
            "npm ci requires a committed lockfile"
        )


def test_compose_does_not_blank_the_api_key():
    """``environment:`` beats ``env_file:`` - an unset host var wipes the key."""
    repo_root = Path(__file__).resolve().parents[2]
    override = repo_root / "docker-compose.override.yml"
    if not override.exists():
        pytest.skip("no local override file")
    text = override.read_text(encoding="utf-8")
    for match in re.finditer(r"OPENROUTER_API_KEY:\s*(\S+)", text):
        value = match.group(1)
        assert "-}" not in value or ":-" in value, (
            "OPENROUTER_API_KEY must not default to an empty string"
        )


def test_compose_only_declares_services_that_exist():
    repo_root = Path(__file__).resolve().parents[2]
    compose = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    services = set(re.findall(r"^  ([a-zA-Z0-9_-]+):\s*$", compose, re.MULTILINE))
    assert "kuzuwiki-worker" not in services, "the worker has no app/agents/worker.py"
    assert "searxng" not in services, "no SearXNG configuration ships with the repo"
    assert "redis" not in services, "no Redis broker exists in the codebase"
    assert "kuzuwiki-backend" in services
    assert "kuzuwiki-frontend" in services


def test_compose_config_validates():
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["docker", "compose", "config", "--quiet"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode == 127:  # pragma: no cover - docker not installed
        pytest.skip("docker is not available")
    assert result.returncode == 0, result.stderr


def test_domain_schemas_are_mounted_into_the_backend():
    repo_root = Path(__file__).resolve().parents[2]
    compose = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    assert "./config/domain_schemas:/config/domain_schemas" in compose


def test_dockerignore_excludes_the_env_file():
    repo_root = Path(__file__).resolve().parents[2]
    dockerignore = (repo_root / ".dockerignore").read_text(encoding="utf-8")
    assert "backend/.env" in dockerignore
    assert "node_modules" in dockerignore


def test_frontend_declares_only_packages_that_exist():
    """``sigma.js`` and ``react-resizable-panels@^0.2`` were never published."""
    import json

    repo_root = Path(__file__).resolve().parents[2]
    package = json.loads((repo_root / "frontend/package.json").read_text(encoding="utf-8"))
    deps = package["dependencies"]
    assert "sigma.js" not in deps, "sigma.js does not exist on npm"
    assert "react-router-dom" not in deps, "no routes are defined, so no router is needed"
    assert "@types/react-markdown" not in deps, "that package does not exist"
    for required in ("sigma", "graphology", "react-resizable-panels", "remark-gfm"):
        assert required in deps, f"{required} is used in the source but not declared"


def test_frontend_has_a_postcss_config():
    """Without it Tailwind never runs and no utility class has any effect."""
    repo_root = Path(__file__).resolve().parents[2]
    assert (repo_root / "frontend/postcss.config.js").exists()
