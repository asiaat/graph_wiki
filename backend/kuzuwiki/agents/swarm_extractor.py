"""Agent 3: JEVSwarmExtractor — virtual expert swarm (Alpha/Beta/Gamma).

Distils unstructured documents into strictly typed nodes, edges and claims
using Lande's *Swarm of Virtual Experts* pattern: heterogeneous personas
inspect the same source in parallel, and only triples that reach a weighted
consensus survive.

Consensus follows AGENTS.md::

    W(u, r, v) = sum_m  omega_m * I[(u, r, v) in E_m] * NLI_score(u, r, v, quote)

with per-expert weights (``omega``) reflecting how much that persona is
trusted for that kind of relation, multiplied by the entailment score of the
triple against its quote.

Failures are *surfaced*: if no expert can be reached the extractor raises
rather than silently returning an empty bundle, because an empty bundle would
compile into an empty graph and look like a successful ingest.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from kuzuwiki.config import settings
from kuzuwiki.jev.nli_verifier import NLI_THRESHOLD, NLIClient, verify_quotebound
from kuzuwiki.jev.schemas import (
    JEVAttackIndexMetrics,
    JEVDistillationBundle,
    JEVExtractedEntity,
    JEVExtractedRelation,
    RelationType,
)
from kuzuwiki.lande.hvg_network import HVGResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Expert:
    """A virtual expert persona."""

    key: str
    system_prompt: str
    temperature: float
    weight: float


#: The exact output contract every expert must satisfy. Without this the
#: models invent their own JSON shape - the first live run returned
#: ``{"registration_id": "...", "agreement_signed": "..."}`` and nothing the
#: compiler could use.
JEV_OUTPUT_CONTRACT = """
You must reply with a single JSON object and nothing else. It must have exactly this shape:

{
  "entities": [
    {
      "canonical_name": "Acme Corporation",
      "category": "Organization",
      "aliases": ["Acme"],
      "deterministic_ids": {"company_number": "08842119"},
      "summary_fact": "One sentence stating what the document says about this entity.",
      "evidence": {
        "source_doc_sha256": "sha",
        "exact_quote": "A contiguous substring of the document, copied character for character.",
        "start_char": 0,
        "end_char": 0
      },
      "confidence": 0.9
    }
  ],
  "relations": [
    {
      "source_entity": "Acme Corporation",
      "target_entity": "Beta Systems",
      "relation_type": "MANUFACTURES",
      "temporal_valid_from": "2024-03-12",
      "temporal_valid_to": null,
      "nli_entailment_score": 0.9,
      "swarm_consensus_count": 1,
      "evidence": {
        "source_doc_sha256": "sha",
        "exact_quote": "A contiguous substring of the document, copied character for character.",
        "start_char": 0,
        "end_char": 0
      }
    }
  ]
}

Rules:
- "category" MUST be one of: Person, Organization, Location, MilitarySystem,
  Component, NarrativeFrame, Event, LegalDocument, FinancialIdentifier.
- "relation_type" MUST be one of: OWNS_CONTROLS, SUPPLIES_COMPONENT, MANUFACTURES,
  FUNDS, AFFILIATED_WITH, AMPLIFIES_NARRATIVE, CONTRADICTS_CLAIM, PARTICIPATED_IN,
  SANCTIONED_UNDER, HIERARCHY_PARENT_OF.
- "exact_quote" MUST be copied verbatim from the document; it is checked
  character for character and a quote that is not present discards the record.
- "source_entity" and "target_entity" MUST exactly match the "canonical_name" of
  an entity you list, or a listed alias.
- Emit only what the document states. Do not infer, do not speculate.
- Empty lists are correct when the document contains nothing of your kind.
"""

ALPHA_PROMPT = (
    """You are Expert Alpha (Conservative Auditor), temperature 0.0.
Extract ONLY explicit, legally/factually stated entities: organisations and people,
serial numbers, registration IDs, dates, financial figures, and authoritative claims.
No speculation.
"""
    + JEV_OUTPUT_CONTRACT
)

BETA_PROMPT = (
    """You are Expert Beta (Relational Investigator), temperature 0.2.
Focus on organisational links, supply-chain dependencies, beneficial ownership,
manufacturing and component supply relationships, and geopolitical affiliations.
"""
    + JEV_OUTPUT_CONTRACT
)

GAMMA_PROMPT = (
    """You are Expert Gamma (Cognitive Warfare Analyst), temperature 0.1.
Focus on narrative frames, emotional manipulation markers, euphemisms, strategic blame
attribution, and entities that carry rhetorical weight (Attack-Index features).
"""
    + JEV_OUTPUT_CONTRACT
)


EXPERTS: tuple[Expert, ...] = (
    Expert("alpha", ALPHA_PROMPT, 0.0, 1.0),
    Expert("beta", BETA_PROMPT, 0.2, 1.0),
    Expert("gamma", GAMMA_PROMPT, 0.1, 0.8),
)


class SwarmExtractionError(RuntimeError):
    """Raised when the swarm cannot produce a usable distillation."""


class SwarmExtractor:
    def __init__(self, openrouter_client=None, nli_client: NLIClient | None = None):
        self.client = openrouter_client or OpenRouterClient(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            primary_model=settings.jev_primary_model,
            fallback_models=settings.fallback_models_list,
        )
        self.nli_client = nli_client or NLIClient(settings.jev_nli_model)

    async def extract(
        self,
        document_text: str,
        doc_sha256: str,
        hvg_hub_terms: list[str],
        slop_metrics: JEVAttackIndexMetrics,
        hvg_result: HVGResult | None = None,
        min_consensus_weight: float = 0.5,
    ) -> JEVDistillationBundle:
        """Run the expert swarm in parallel and aggregate weighted consensus."""
        raw_text = document_text[:10000]  # Cap for model context

        results = await asyncio.gather(
            *(self._run_expert(expert, raw_text) for expert in EXPERTS),
            return_exceptions=True,
        )

        expert_outputs: list[dict[str, Any]] = []
        failures: list[str] = []
        for expert, outcome in zip(EXPERTS, results, strict=False):
            if isinstance(outcome, Exception):
                failures.append(f"{expert.key}: {outcome}")
                continue
            expert_outputs.append(outcome)

        if not expert_outputs:
            raise SwarmExtractionError(
                "Every virtual expert failed; the distillation would be empty. "
                + "; ".join(failures)
            )
        if failures:
            logger.warning("Swarm degraded - %s", "; ".join(failures))

        all_entities = [e for out in expert_outputs for e in out["entities"]]
        all_relations = [r for out in expert_outputs for r in out["relations"]]

        consensus_entities = self._consensus_entities(all_entities)
        consensus_relations = self._consensus_relations(
            all_relations, document_text, min_consensus_weight
        )

        return JEVDistillationBundle(
            doc_sha256=doc_sha256,
            lande_hub_terms=hvg_hub_terms,
            metrics=slop_metrics,
            entities=consensus_entities,
            relations=consensus_relations,
            hvg_edges=[
                {
                    "term_a": edge.term_a,
                    "term_b": edge.term_b,
                    "visibility_weight": edge.visibility_weight,
                    "direction": edge.direction,
                }
                for edge in (hvg_result.edges if hvg_result else [])
            ],
            term_weights=dict(hvg_result.term_weights) if hvg_result else {},
            burst_terms=list(hvg_result.burst_terms) if hvg_result else [],
        )

    async def _run_expert(self, expert: Expert, text: str) -> dict[str, Any]:
        """Run one virtual expert against OpenRouter, with model fallbacks."""
        try:
            response = await self.client.chat_completion(
                system_prompt=expert.system_prompt,
                text=text,
                temperature=expert.temperature,
            )
            return self._parse_expert_response(response)
        except Exception as exc:
            logger.error("Expert %s failed on primary model: %s", expert.key, exc)
            for fallback_model in self.client.fallback_models:
                try:
                    response = await self.client.chat_completion(
                        model_override=fallback_model,
                        system_prompt=expert.system_prompt,
                        text=text,
                        temperature=expert.temperature,
                    )
                    return self._parse_expert_response(response)
                except Exception as exc2:
                    logger.error("Fallback %s failed: %s", fallback_model, exc2)
            raise

    def _parse_expert_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """Parse the expert's JSON payload, tolerating code fences."""
        content = response.get("content") or "{}"
        if isinstance(content, list):  # some providers return content parts
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        text = str(content).strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip("`").strip()
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise SwarmExtractionError(f"Expert returned non-JSON payload: {exc}") from exc

        if isinstance(parsed, list):
            # A bare array is interpreted as a list of entities.
            parsed = {"entities": parsed}
        if not isinstance(parsed, dict):
            raise SwarmExtractionError("Expert payload was not a JSON object")

        entities = parsed.get("entities")
        relations = parsed.get("relations")
        if entities is None and relations is None:
            # The model ignored the contract and returned some other shape.
            # Try the most common near-misses before giving up.
            entities = parsed.get("entity") or parsed.get("extracted_entities")
            relations = parsed.get("relation") or parsed.get("extracted_relations")
            if entities or relations:
                logger.warning(
                    "Expert returned an unrecognised envelope; coerced keys: %s",
                    sorted(parsed),
                )

        return {
            "entities": list(entities or []),
            "relations": list(relations or []),
        }

    def _consensus_entities(self, all_entities: list[dict[str, Any]]) -> list[JEVExtractedEntity]:
        """Merge entities from all three experts; deduplicate by canonical name."""
        seen: dict[str, JEVExtractedEntity] = {}
        rejected = 0
        for raw in all_entities:
            name = str(raw.get("canonical_name", "")).strip()
            if not name:
                rejected += 1
                continue
            key = name.lower()
            try:
                entity = JEVExtractedEntity(**raw)
            except Exception as exc:
                logger.warning("Discarding malformed entity %r: %s", name, exc)
                rejected += 1
                continue
            existing = seen.get(key)
            if existing is None:
                seen[key] = entity
            else:
                # Merge aliases and keep the strongest confidence.
                merged = list(dict.fromkeys([*existing.aliases, *entity.aliases]))
                existing.aliases = merged
                existing.confidence = max(existing.confidence, entity.confidence)
        if rejected:
            logger.warning("%d extracted entity record(s) failed schema validation", rejected)
        return list(seen.values())

    def _consensus_relations(
        self,
        all_relations: list[dict[str, Any]],
        document_text: str,
        min_consensus_weight: float = 0.5,
    ) -> list[JEVExtractedRelation]:
        """Aggregate relations, apply the weighted consensus and the NLI gate."""
        weights: dict[tuple[str, str, str], float] = {}
        votes: dict[tuple[str, str, str], int] = {}
        objects: dict[tuple[str, str, str], JEVExtractedRelation] = {}
        rejected = 0

        for raw in all_relations:
            key = (
                str(raw.get("source_entity", "")).strip(),
                str(raw.get("relation_type", "")).strip(),
                str(raw.get("target_entity", "")).strip(),
            )
            if not all(key):
                rejected += 1
                continue
            try:
                relation = JEVExtractedRelation(**raw)
            except Exception as exc:
                logger.warning("Discarding malformed relation %r: %s", key, exc)
                rejected += 1
                continue
            objects.setdefault(key, relation)
            votes[key] = votes.get(key, 0) + 1
            weights[key] = weights.get(key, 0.0) + self._expert_weight_for(raw)

        accepted: list[JEVExtractedRelation] = []
        for key, vote_count in votes.items():
            relation = objects[key]
            relation.swarm_consensus_count = min(5, vote_count)

            result = verify_quotebound(
                relation, document_text, strict=True, backend=self.nli_client.backend
            )
            relation.nli_entailment_score = result.entailment_score
            if not result.quote_verified:
                logger.debug("Relation %s rejected: %s", key, result.reject_reason)
                continue
            if not result.pass_or_fail:
                logger.debug(
                    "Relation %s rejected: entailment %.3f below threshold %.2f",
                    key,
                    result.entailment_score,
                    NLI_THRESHOLD,
                )
                continue

            # W = sum(omega_m) * NLI_score, normalised by the number of experts.
            consensus_weight = (weights.get(key, 0.0) * result.entailment_score) / len(EXPERTS)
            relation.weight = round(min(1.0, consensus_weight), 4)
            if relation.weight < min_consensus_weight:
                logger.debug(
                    "Relation %s below consensus threshold (%.3f < %.2f)",
                    key,
                    relation.weight,
                    min_consensus_weight,
                )
                continue
            accepted.append(relation)

        return accepted

    @staticmethod
    def _expert_weight_for(raw: dict[str, Any]) -> float:
        """Weight a relation by the expertise of the persona that proposed it.

        The persona is not transmitted over the wire, so the weight is derived
        from the relation type: relational types are Alpha/Beta's domain,
        narrative types are Gamma's.
        """
        try:
            relation_type = RelationType(str(raw.get("relation_type", "")))
        except ValueError:
            return 0.5
        narrative = {
            RelationType.AMPLIFIES_NARRATIVE,
            RelationType.CONTRADICTS_CLAIM,
        }
        factual = {
            RelationType.MANUFACTURES,
            RelationType.SUPPLIES_COMPONENT,
            RelationType.OWNS_CONTROLS,
            RelationType.FUNDS,
            RelationType.SANCTIONED_UNDER,
            RelationType.PARTICIPATED_IN,
        }
        if relation_type in narrative:
            return 0.8
        if relation_type in factual:
            return 1.0
        return 0.6


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        primary_model: str | None = None,
        fallback_models: list[str] | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = primary_model or "nvidia/nemotron-3-8b-32k-instruct:free"
        self.fallback_models = fallback_models or [
            "google/gemma-3-27b-it:free",
            "google/flint-8b:free",
            "minimax/minimax-01:free",
        ]

    async def chat_completion(
        self,
        system_prompt: str,
        text: str,
        model_override: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Send a chat completion to OpenRouter with automatic model fallback."""
        model = model_override or self.model
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text},
                    ],
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            message = data.get("choices", [{}])[0].get("message", {})
            return message if isinstance(message, dict) else {}
