"""Layer 3: declarative domain schema packs.

Each pack under ``config/domain_schemas/`` declares, for one analysis domain:

* ``lande_stopwords``    - tokens excluded from the visibility graph;
* ``entity_types``      - the entity taxonomy of the domain;
* ``edge_types``        - the relationship vocabulary of the domain;
* ``osint_templates``   - search queries the OSINT agent can dispatch;
* ``attack_index``      - detection thresholds (wave sigma, reprint cutoff).

The packs are the governance layer: the pipeline validates what it extracts
against them instead of trusting whatever the model produced.

Lookup order for the schema directory:

1. ``$DOMAIN_SCHEMA_PATH``
2. ``<repo root>/config/domain_schemas`` (development)
3. ``/config/domain_schemas`` (container)
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class OsintTemplate(BaseModel):
    name: str
    query: str
    description: str = ""


class AttackIndexConfig(BaseModel):
    wave_threshold_sigma: float = 2.5
    reprint_threshold: float = 0.85
    emotional_intensity_threshold: float = 0.6


class DomainSchema(BaseModel):
    """One declarative domain pack."""

    version: str = "1.0"
    domain: str
    lande_stopwords: list[str] = Field(default_factory=list)
    entity_types: list[str] = Field(default_factory=list)
    edge_types: list[str] = Field(default_factory=list)
    osint_templates: list[OsintTemplate] = Field(default_factory=list)
    attack_index: AttackIndexConfig = Field(default_factory=AttackIndexConfig)
    source_path: str = ""

    def stopword_set(self) -> set[str]:
        return {w.lower() for w in self.lande_stopwords}

    def dorks_for(self, entity_name: str) -> list[str]:
        """Render the OSINT search templates for an entity."""
        rendered = []
        for template in self.osint_templates:
            try:
                rendered.append(
                    template.query.format(
                        entity_name=entity_name,
                        entity=entity_name,
                        hs_code="",
                        domain=self.domain,
                    )
                )
            except (KeyError, IndexError):
                logger.debug("Unrenderable OSINT template: %s", template.query)
        return rendered


def _candidate_dirs() -> list[Path]:
    candidates: list[Path] = []
    env_path = os.environ.get("DOMAIN_SCHEMA_PATH")
    if env_path:
        candidates.append(Path(env_path))
    # backend/kuzuwiki/lande/domain_schema.py -> repo root is three levels up.
    repo_root = Path(__file__).resolve().parents[3]
    candidates.append(repo_root / "config" / "domain_schemas")
    candidates.append(Path("/config/domain_schemas"))
    return candidates


def schema_dir() -> Path | None:
    """Locate the directory holding the domain packs."""
    for candidate in _candidate_dirs():
        if candidate.is_dir() and any(candidate.glob("*.yaml")):
            return candidate
    return None


@lru_cache(maxsize=1)
def load_all_schemas() -> dict[str, DomainSchema]:
    """Load every domain pack, keyed by its ``domain`` name."""
    directory = schema_dir()
    if directory is None:
        logger.warning("No domain schema directory found; using built-in defaults")
        return {}
    schemas: dict[str, DomainSchema] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            logger.error("Could not parse domain pack %s: %s", path, exc)
            continue
        raw["source_path"] = str(path)
        try:
            schema = DomainSchema(**raw)
        except Exception as exc:
            logger.error("Invalid domain pack %s: %s", path, exc)
            continue
        schemas[schema.domain] = schema
    logger.info("Loaded %d domain packs from %s", len(schemas), directory)
    return schemas


def load_schema(domain: str | None) -> DomainSchema | None:
    """Load one domain pack by name. Returns ``None`` when unknown."""
    if not domain:
        return None
    schemas = load_all_schemas()
    schema = schemas.get(domain.strip().lower())
    if schema is None:
        for candidate in schemas.values():
            if candidate.domain.replace("_", "-") == domain.strip().lower().replace("_", "-"):
                return candidate
    return schema


def default_stopwords() -> set[str]:
    """Stopwords to use when no domain pack applies."""
    schemas = load_all_schemas()
    if len(schemas) == 1:
        only = next(iter(schemas.values()))
        return only.stopword_set()
    merged: set[str] = set()
    for schema in schemas.values():
        merged |= schema.stopword_set()
    return merged
