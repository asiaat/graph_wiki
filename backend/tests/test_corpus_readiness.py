"""WP-1 gate: the pipeline must be able to take an open-source corpus.

Covers the four adaptations the Berlin-2026 corpus forced:

* **source typing** - an analyst assessment has no publisher and no web
  domain, so rating it "cannot be judged" was wrong;
* **chunking** - 10 of the 52 corpus documents exceed the 10,000-character
  window the experts used to see, and everything past the cut was dropped;
* **sensitivity** - contact identifiers and persons of interest must be
  tagged so they can be filtered or stripped before publication;
* **domain packs** - the packs must be selectable, not merely merged.
"""

from __future__ import annotations

import json

import pytest

from kuzuwiki.jev.admiralty import classify_source
from kuzuwiki.jev.chunking import chunk_document
from kuzuwiki.jev.schemas import (
    EntityCategory,
    JEVExtractedEntity,
    RelationType,
    Sensitivity,
    SourceType,
    default_sensitivity_for,
)
from kuzuwiki.lande.domain_schema import (
    load_all_schemas,
    load_schema,
    schema_for,
    stopwords_for,
)

# --------------------------------------------------------------- source type


def test_analyst_report_is_not_rated_cannot_be_judged():
    """An analyst dossier has no publisher domain; rating it F was wrong."""
    assessment = classify_source(
        "Findings: Mundfish has no connection to the Berlin attack.",
        domain=None,
        source_type=SourceType.ANALYST_REPORT,
    )
    assert assessment.reliability.value.startswith("C")
    assert assessment.credibility_rank <= 4
    assert "analyst" in assessment.rationale


def test_official_record_outranks_an_analyst_report():
    official = classify_source("", domain=None, source_type=SourceType.OFFICIAL_RECORD)
    analyst = classify_source("", domain=None, source_type=SourceType.ANALYST_REPORT)
    assert official.reliability.value.startswith("A")
    assert analyst.reliability.value.startswith("C")


def test_web_article_still_uses_the_domain_priors():
    """Typed sources bypass the domain path; web articles must not."""
    assessment = classify_source(
        "According to officials, the registry confirmed the filing.",
        domain="reuters.com",
        source_type=SourceType.WEB_ARTICLE,
    )
    assert assessment.reliability.value.startswith("A")


def test_unknown_web_domain_still_falls_back_to_content_signals():
    assessment = classify_source(
        "Some unstructured claim with no attribution whatsoever.",
        domain="unknown-blog.example",
        source_type=SourceType.WEB_ARTICLE,
    )
    assert assessment.reliability.value in {
        "D_NOT_USUALLY_RELIABLE",
        "E_UNRELIABLE",
        "F_CANNOT_BE_JUDGED",
    }


# ------------------------------------------------------------------ chunking


def test_short_document_is_one_chunk():
    chunks = chunk_document("A short report about Acme Corporation.")
    assert len(chunks) == 1
    assert chunks[0].text.startswith("A short report")


def test_long_document_is_split_and_nothing_is_lost():
    body = "\n\n".join(
        f"## Section {i}\n\nContent for section {i}. " + ("Detail text. " * 20) for i in range(40)
    )
    assert len(body) > 2000
    chunks = chunk_document(body, max_chars=2000)
    assert len(chunks) > 1
    # Every chunk must be within the window.
    assert all(len(c.text) <= 2000 for c in chunks)
    # And the union must cover the document.
    assert "".join(c.text for c in chunks).count("Content for section") == 40


def test_chunk_offsets_point_at_the_original_text():
    body = "## Alpha\n\nFirst body text.\n\n## Beta\n\nSecond body text."
    chunks = chunk_document(body, max_chars=40)
    for chunk in chunks:
        assert body[chunk.start_char : chunk.end_char] == chunk.text


def test_a_quote_past_the_truncation_point_is_still_found():
    """The regression this whole change exists for.

    A 37,088-character report used to lose everything after character 10,000.
    """
    filler = "Filler sentence about the weather. "
    document = filler * 400 + "Acme Corporation manufactures the X-200 airframe."
    assert len(document) > 10000

    chunks = chunk_document(document, max_chars=8000)
    assert len(chunks) > 1

    # The tail lives in the last chunk, and the quote is locatable in the
    # *whole* document - which is what the entailment gate searches.
    assert "X-200 airframe" in chunks[-1].text
    from kuzuwiki.jev.nli_verifier import locate_quote

    start, end = locate_quote("Acme Corporation manufactures the X-200 airframe.", document)
    assert start > 10000, "the quote should sit past the old truncation point"
    assert end == start + len("Acme Corporation manufactures the X-200 airframe.")


def test_a_quote_spanning_a_chunk_boundary_still_verifies():
    from kuzuwiki.jev.nli_verifier import locate_quote

    # Force a boundary in the middle of the sentence.
    prefix = "x" * 7990
    document = prefix + "Acme Corporation manufactures the X-200 airframe for Beta Systems."
    chunks = chunk_document(document, max_chars=8000)
    assert len(chunks) >= 2
    span = locate_quote(
        "Acme Corporation manufactures the X-200 airframe for Beta Systems.", document
    )
    assert span is not None, "a quote across the boundary must still be locatable"


# --------------------------------------------------------------- sensitivity


@pytest.mark.parametrize(
    "category",
    [
        EntityCategory.PHONE_NUMBER,
        EntityCategory.EMAIL_ADDRESS,
        EntityCategory.TELEGRAM_CHANNEL,
        EntityCategory.RISK_INDICATOR,
        EntityCategory.PERSON,
    ],
)
def test_contact_and_person_categories_are_sensitive(category: EntityCategory):
    assert default_sensitivity_for(category) == Sensitivity.SENSITIVE


@pytest.mark.parametrize(
    "category",
    [EntityCategory.ORGANIZATION, EntityCategory.LOCATION, EntityCategory.EVENT],
)
def test_ordinary_categories_are_public(category: EntityCategory):
    assert default_sensitivity_for(category) == Sensitivity.PUBLIC


def test_sensitivity_can_be_set_explicitly_on_an_entity():
    entity = JEVExtractedEntity(
        canonical_name="Subject A",
        category=EntityCategory.ORGANIZATION,
        summary_fact="A subject of an allegation.",
        evidence={
            "source_doc_sha256": "sha",
            "exact_quote": "A sufficiently long quote for the schema to accept.",
        },
        sensitivity=Sensitivity.RESTRICTED,
    )
    assert entity.sensitivity == Sensitivity.RESTRICTED


# -------------------------------------------------------------- domain packs


def test_the_osint_pack_exists_and_is_loadable():
    schema = load_schema("osint_berlin26")
    assert schema is not None
    assert "Person" in schema.entity_types
    assert "TelegramChannel" in schema.entity_types
    assert "LOCATED_IN" in schema.edge_types
    assert schema.attack_index.reprint_threshold == 0.85


def test_all_four_packs_load():
    schemas = load_all_schemas()
    assert set(schemas) >= {
        "drone_supply_chain",
        "hybrid_warfare",
        "corporate_osint",
        "osint_berlin26",
    }


def test_a_named_domain_gets_only_its_own_stopwords():
    """Merging every pack would apply one domain's vocabulary to another."""
    drone = stopwords_for("drone_supply_chain")
    osint = stopwords_for("osint_berlin26")
    assert drone != osint
    # "evidence" is an analyst-report filler word, not a drone word.
    assert "evidence" in osint
    assert "evidence" not in drone


def test_unknown_domain_falls_back_to_the_merged_set():
    merged = stopwords_for(None)
    assert merged
    unknown = stopwords_for("no-such-domain")
    assert unknown == merged


def test_schema_for_returns_the_pack():
    assert schema_for("osint_berlin26") is not None
    assert schema_for("nope") is None
    assert schema_for(None) is None


# --------------------------------------------------------------- extensions


def test_the_new_entity_categories_exist():
    for name in (
        "TelegramChannel",
        "Website",
        "PhoneNumber",
        "EmailAddress",
        "Infrastructure",
        "Group",
        "PoliticalParty",
        "ServiceProvider",
        "RiskIndicator",
        "JobType",
    ):
        assert EntityCategory(name).value == name


def test_the_new_relation_types_exist():
    for name in (
        "LOCATED_IN",
        "OPERATES_FROM",
        "RECRUITS_FROM",
        "ATTACKED",
        "COMMUNICATES_WITH",
    ):
        assert RelationType(name).value == name


def test_relation_types_are_json_serialisable():
    """They cross the wire to the frontend."""
    assert json.dumps({"t": RelationType.LOCATED_IN.value}) == '{"t": "LOCATED_IN"}'
