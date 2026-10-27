"""WP-1 / WP-2 gate: every backend module must import cleanly.

Regression guard for three historic blockers:
  * ``lande/attack_index.py``  - ``from __future__`` after another import
  * ``lande/reprint_cascade.py`` - ``Optional`` used but never imported
  * ``agents/orchestrator.py`` - import of the nonexistent ``swagger_extractor``

Also guards the package rename: ``app`` was a namespace package that could be
shadowed by an unrelated ``app`` package elsewhere on ``sys.path``.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import kuzuwiki

MODULES = [
    "kuzuwiki.config",
    "kuzuwiki.main",
    "kuzuwiki.db.kuzu_client",
    "kuzuwiki.db.schema_init",
    "kuzuwiki.db.wiki_sync",
    "kuzuwiki.jev.schemas",
    "kuzuwiki.jev.slop_classifier",
    "kuzuwiki.jev.nli_verifier",
    "kuzuwiki.jev.entity_resolver",
    "kuzuwiki.lande.hvg_network",
    "kuzuwiki.lande.attack_index",
    "kuzuwiki.lande.reprint_cascade",
    "kuzuwiki.agents.gatekeeper",
    "kuzuwiki.agents.swarm_extractor",
    "kuzuwiki.agents.wiki_compiler",
    "kuzuwiki.agents.linter_agent",
    "kuzuwiki.agents.osint_complicator",
    "kuzuwiki.agents.orchestrator",
    "kuzuwiki.api.routes_ingest",
    "kuzuwiki.api.routes_graph",
    "kuzuwiki.api.routes_wiki",
    "kuzuwiki.api.routes_osint",
]


def test_package_is_a_regular_package():
    """``app`` used to be a namespace package and could be shadowed."""
    assert kuzuwiki.__file__ is not None
    assert kuzuwiki.__file__.endswith("__init__.py")


@pytest.mark.parametrize("module_name", MODULES)
def test_module_imports(module_name: str):
    assert importlib.import_module(module_name) is not None


def test_no_module_uses_the_fictional_kuzudb_package():
    """``kuzudb`` never existed on PyPI; the real distribution is ``kuzu``."""
    import pathlib
    import re

    root = pathlib.Path(kuzuwiki.__file__).parent
    pattern = re.compile(r"^\s*(?:import\s+kuzudb\b|from\s+kuzudb\s)", re.MULTILINE)
    offenders = [
        str(p.relative_to(root)) for p in root.rglob("*.py") if pattern.search(p.read_text())
    ]
    assert offenders == [], f"stale 'kuzudb' imports: {offenders}"


def test_every_subpackage_has_init():
    import pathlib

    root = pathlib.Path(kuzuwiki.__file__).parent
    for path in root.rglob("*"):
        if path.is_dir() and path.name != "__pycache__":
            assert (path / "__init__.py").exists(), f"missing __init__.py in {path}"


def test_all_submodules_discovered():
    """Every .py under the package must be importable, not just the listed ones."""
    root = importlib.import_module("kuzuwiki").__path__[0]
    failures = []
    for mod in pkgutil.walk_packages([root], prefix="kuzuwiki."):
        try:
            importlib.import_module(mod.name)
        except Exception as exc:  # pragma: no cover - failure path
            failures.append(f"{mod.name}: {exc!r}")
    assert failures == []
