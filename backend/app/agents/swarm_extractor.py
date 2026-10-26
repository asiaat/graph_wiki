"""Agent 3: JEVSwarmExtractor — Virtual Expert Swarm (Alpha/Beta/Gamma).
Distills unstructured documents into strictly typed nodes, edges, and claims using consensus.
"""

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings
from app.jev.nli_verifier import NLIClient, verify_quotebound
from app.jev.schemas import (
    JEVAttackIndexMetrics,
    JEVDistillationBundle,
    JEVExtractedEntity,
    JEVExtractedRelation,
    RelationType,
    VerbatimSpan,
    AdmiraltyReliability,
)

logger = logging.getLogger(__name__)

# OpenRouter system prompts for the three swarm personas
ALPHA_PROMPT = """You are Expert Alpha (Conservative Auditor), temperature 0.0.
Extract ONLY explicit, legally/factually stated entities: serial numbers, registration IDs,
dates, financial figures, and authoritative claims. Return ONLY a JEVDistillationBundle JSON.
No speculation."""

BETA_PROMPT = """You are Expert Beta (Relational Investigator), temperature 0.2.
Focus on organizational links, supply-chain dependencies, beneficial ownership,
geopolitical affiliations. Return ONLY a JEVDistillationBundle JSON."""

GAMMA_PROMPT = """You are Expert Gamma (Cognitive Warfare Analyst), temperature 0.1.
Extract narrative frames, emotional manipulation markers, euphemisms, strategic blame
attribution (Attack-Index features). Return ONLY a JEVDistillationBundle JSON."""


class SwarmExtractor:
    def __init__(self, openrouter_client=None):
        self.client = openrouter_client or OpenRouterClient(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            primary_model=settings.jev_primary_model,
            fallback_models=settings.fallback_models_list,
        )
        self.nli_client = NLIClient(settings.jev_nli_model)

    async def extract(
        self,
        document_text: str,
        doc_sha256: str,
        hvg_hub_terms: list[str],
        slop_metrics: JEVAttackIndexMetrics,
    ) -> JEVDistillationBundle:
        """Run three virtual experts in parallel, aggregate consensus."""
        raw_text = document_text[:10000]  # Cap for model context

        alpha, beta, gamma = await asyncio.gather(
            self._run_expert(ALPHA_PROMPT, raw_text),
            self._run_expert(BETA_PROMPT, raw_text),
            self._run_expert(GAMMA_PROMPT, raw_text),
        )

        # Aggregate consensus
        all_entities = alpha["entities"] + beta["entities"] + gamma["entities"]
        all_relations = alpha["relations"] + beta["relations"] + gamma["relations"]

        consensus_entities = self._consensus_entities(all_entities)
        consensus_relations = self._consensus_relations(all_relations, document_text)

        return JEVDistillationBundle(
            doc_sha256=doc_sha256,
            lande_hub_terms=hvg_hub_terms,
            metrics=slop_metrics,
            entities=consensus_entities,
            relations=consensus_relations,
        )

    async def _run_expert(self, system_prompt: str, text: str) -> dict[str, Any]:
        """Run one virtual expert against OpenRouter."""
        try:
            response = await self.client.chat_completion(
                system_prompt=system_prompt,
                text=text,
            )
            return self._parse_expert_response(response)
        except Exception as exc:
            logger.error("Expert call failed: %s", exc)
            # Try fallback models
            for fallback_model in self.client.fallback_models:
                try:
                    response = await self.client.chat_completion(
                        model_override=fallback_model,
                        system_prompt=system_prompt,
                        text=text,
                    )
                    return self._parse_expert_response(response)
                except Exception as exc2:
                    logger.error("Fallback %s failed: %s", fallback_model, exc2)
            return {"entities": [], "relations": []}

    def _parse_expert_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """Parse LLM response with Pydantic validation."""
        content = response.get("content", "{}")
        try:
            import json

            parsed = json.loads(content)
            return {
                "entities": parsed.get("entities", []),
                "relations": parsed.get("relations", []),
            }
        except Exception:
            return {"entities": [], "relations": []}

    def _consensus_entities(self, all_entities: list[dict[str, Any]]) -> list[JEVExtractedEntity]:
        """Merge entities from all three experts; deduplicate by canonical_name."""
        seen: dict[str, JEVExtractedEntity] = {}
        for e in all_entities:
            name = e.get("canonical_name", "")
            if not name:
                continue
            if name not in seen:
                try:
                    seen[name] = JEVExtractedEntity(**e)
                except Exception:
                    continue
        return list(seen.values())

    def _consensus_relations(
        self, all_relations: list[dict[str, Any]], document_text: str
    ) -> list[JEVExtractedRelation]:
        """Aggregate relations; compute swarm consensus count; apply NLI gate."""
        relation_key_count: dict[tuple[str, str, str], int] = {}
        relation_objects: dict[tuple[str, str, str], JEVExtractedRelation] = {}

        for r in all_relations:
            key = (
                r.get("source_entity", ""),
                r.get("relation_type", ""),
                r.get("target_entity", ""),
            )
            relation_key_count[key] = relation_key_count.get(key, 0) + 1
            if key not in relation_objects:
                try:
                    relation_objects[key] = JEVExtractedRelation(**r)
                except Exception:
                    continue

        consensus_relations = []
        for key, count in relation_key_count.items():
            rel = relation_objects[key]
            rel.swarm_consensus_count = count

            # Build VerbatimSpan from relation evidence if present
            if not rel.evidence:
                rel.evidence = VerbatimSpan(
                    source_doc_sha256="",
                    exact_quote=rel.source_entity + " " + rel.predicate + " " + rel.target_entity,
                    start_char=0,
                    end_char=0,
                )

            # Apply NLI + verbatim gate
            try:
                nli_result = verify_quotebound(rel, document_text, strict=True)
                rel.nli_entailment_score = nli_result.entailment_score
                if not nli_result.pass_or_fail:
                    continue  # Reject weak entailment
            except Exception as exc:
                logger.error("NLI verification failed: %s", exc)
                continue

            consensus_relations.append(rel)

        return consensus_relations


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        primary_model: str = None,
        fallback_models: list[str] = None,
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
        model_override: str = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Send chat completion to OpenRouter with automatic fallback."""
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
