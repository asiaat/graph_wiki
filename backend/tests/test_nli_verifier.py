"""WP-5 gate: the entailment / verbatim grounding gate.

The old implementation scored the *quote* against the two *entity names*,
which meant a realistic, perfectly grounded sentence scored 0.0 and the gate
rejected 100% of relations. These tests pin the corrected behaviour.
"""

from __future__ import annotations

import pytest

from kuzuwiki.jev.nli_verifier import (
    NLI_THRESHOLD,
    NLIClient,
    locate_quote,
    score_entailment,
    verify_quotebound,
)
from kuzuwiki.jev.schemas import JEVExtractedRelation, RelationType, VerbatimSpan

DOC = (
    "Acme Corporation manufactures the X-200 drone airframe for Beta Systems. "
    "In 2024, Beta Systems supplied rotor components to Acme Corporation under "
    "a framework agreement signed in March 2024. Independent analysts reported "
    "that the European market grew by 12 percent that year."
)


def _relation(
    source: str,
    target: str,
    rel: RelationType,
    quote: str,
    start: int = 0,
    end: int = 0,
    temporal: str | None = None,
) -> JEVExtractedRelation:
    return JEVExtractedRelation(
        source_entity=source,
        target_entity=target,
        relation_type=rel,
        nli_entailment_score=0.9,
        swarm_consensus_count=3,
        temporal_valid_from=temporal,
        evidence=VerbatimSpan(
            source_doc_sha256="sha",
            exact_quote=quote,
            start_char=start,
            end_char=end,
        ),
    )


def test_grounded_quote_passes_the_gate():
    quote = "Acme Corporation manufactures the X-200 drone airframe for Beta Systems."
    rel = _relation("Acme Corporation", "Beta Systems", RelationType.MANUFACTURES, quote)
    result = verify_quotebound(rel, DOC)
    assert result.quote_verified
    assert result.is_entailed
    assert result.entailment_score >= NLI_THRESHOLD
    assert result.pass_or_fail
    assert result.reject_reason is None
    assert result.predicate_matched


def test_scores_are_calibrated_not_degenerate():
    """The old gate returned 0.0 for realistic quotes - guard against a repeat."""
    quote = "Acme Corporation manufactures the X-200 drone airframe for Beta Systems."
    rel = _relation("Acme Corporation", "Beta Systems", RelationType.MANUFACTURES, quote)
    score, details = score_entailment(rel, quote)
    assert score > 0.85
    assert details["entities_present"]
    assert details["source_coverage"] == 1.0
    assert details["target_coverage"] == 1.0


def test_unrelated_quote_is_rejected():
    quote = "Independent analysts reported that the European market grew by 12 percent that year."
    rel = _relation("Acme Corporation", "Beta Systems", RelationType.MANUFACTURES, quote)
    result = verify_quotebound(rel, DOC)
    assert not result.is_entailed
    assert not result.pass_or_fail
    assert result.reject_reason == "quote_does_not_name_both_entities"


def test_quote_absent_from_source_is_rejected():
    quote = "Gamma Holdings secretly funds the entire operation."
    rel = _relation("Gamma Holdings", "Delta Group", RelationType.FUNDS, quote)
    result = verify_quotebound(rel, DOC)
    assert not result.quote_verified
    assert not result.pass_or_fail
    assert result.reject_reason == "quote_not_found_in_source"


def test_wrong_offsets_are_corrected_not_rejected():
    """LLM offsets are unreliable; the quote itself is the contract."""
    quote = "Beta Systems supplied rotor components to Acme Corporation under"
    rel = _relation(
        "Beta Systems",
        "Acme Corporation",
        RelationType.SUPPLIES_COMPONENT,
        quote,
        start=9999,
        end=9999,
    )
    result = verify_quotebound(rel, DOC)
    assert result.quote_verified
    assert result.grounded_start == DOC.find(quote)
    assert result.grounded_end == DOC.find(quote) + len(quote)


def test_wrong_relation_type_scores_lower():
    quote = "Acme Corporation manufactures the X-200 drone airframe for Beta Systems."
    good = _relation("Acme Corporation", "Beta Systems", RelationType.MANUFACTURES, quote)
    bad = _relation("Acme Corporation", "Beta Systems", RelationType.FUNDS, quote)
    good_score, _ = score_entailment(good, quote)
    bad_score, _ = score_entailment(bad, quote)
    assert good_score > bad_score


def test_temporal_conflict_is_penalised():
    quote = "In 2024, Beta Systems supplied rotor components to Acme Corporation under"
    ok = _relation(
        "Beta Systems",
        "Acme Corporation",
        RelationType.SUPPLIES_COMPONENT,
        quote,
        temporal="2024-01",
    )
    bad = _relation(
        "Beta Systems",
        "Acme Corporation",
        RelationType.SUPPLIES_COMPONENT,
        quote,
        temporal="2019-01",
    )
    ok_score, _ = score_entailment(ok, quote)
    bad_score, _ = score_entailment(bad, quote)
    assert ok_score > bad_score


def test_locate_quote_tolerates_whitespace_reflow():
    text = "Acme Corporation   manufactures\nthe X-200 airframe."
    assert locate_quote("Acme Corporation manufactures the X-200 airframe.", text) is not None


def test_nli_client_batch_returns_one_result_per_relation():
    quote = "Acme Corporation manufactures the X-200 drone airframe for Beta Systems."
    rel = _relation("Acme Corporation", "Beta Systems", RelationType.MANUFACTURES, quote)
    client = NLIClient()
    results = client.verify_batch([rel, rel], DOC)
    assert len(results) == 2
    assert all(r.pass_or_fail for r in results)
    assert results[0].backend == "lexical"


@pytest.mark.parametrize(
    "relation_type",
    [
        RelationType.MANUFACTURES,
        RelationType.SUPPLIES_COMPONENT,
        RelationType.FUNDS,
        RelationType.OWNS_CONTROLS,
        RelationType.PARTICIPATED_IN,
        RelationType.SANCTIONED_UNDER,
    ],
)
def test_every_relation_type_has_triggers(relation_type: RelationType):
    from kuzuwiki.jev.nli_verifier import RELATION_TRIGGERS

    assert RELATION_TRIGGERS.get(relation_type), f"no triggers for {relation_type}"
