# Implementation Plan

## Product objective

Prove the product's core promise with one usable analyst workflow: ingest a
source document, compile traceable claims, query those claims, and return either
source-backed findings or an explicit evidence gap.

## Milestone 1 — Evidence-backed analyst query

**Status: implemented in the working tree; automated validation passed.**

- Query claims from the compiled graph and rank them against analyst terms.
- Show a claim only when confidence is at least 0.70, NLI entailment is at least
  0.85, the claim has a quote linked to a source document, and it has no
  unresolved contradiction.
- Return `INSUFFICIENT_VERIFIED_EVIDENCE` and open an `OSINTGapTicket` when no
  matching claim meets those requirements.
- Let analysts review gap tickets and optionally file supported findings as a
  synthesis concept.
- Make directed entity relationships readable in both the graph canvas and wiki
  dossiers, including the supporting source quote and clickable entity links.
- Keep query behavior explicit: this milestone returns evidence-backed claims;
  it does not generate natural-language conclusions or infer missing links.

## Milestone 2 — Corpus proof

Use the `osint_berlin26` domain pack with a representative, permission-cleared
corpus. Measure ingestion completion, source-span validity, claim qualification
rate, and the share of analyst questions that correctly return findings versus
an evidence-gap ticket. Fix corpus-specific loss or misclassification before
adding another domain.

**Entry condition:** corpus location, provenance, and handling restrictions are
documented. The repository currently has the domain pack and corpus-readiness
tests, but no corpus files were found in the workspace.

## Milestone 3 — Reliable operations

- Review the new working-tree changes as one coherent release and reconcile
  tests, docs, and configuration with actual code.
- Designate one KùzuDB writer. The current Celery worker opens the embedded
  database itself, so do not enable it beside the API until writes are routed
  through a single owner or another supported concurrency model is established.
- Add Redis/worker services only after that writer boundary and health behavior
  are in place.
- Record operational measures: ingestion failures, rejected documents,
  unsupported-query rate, and ticket review time.

## Milestone 4 — Expand retrieval and research

After the corpus proof, prioritize the largest observed analyst pain. Candidate
work includes multi-hop query traversal, semantic retrieval, a real-time graph
event stream, and autonomous OSINT ticket execution. Each addition should
preserve source attribution and the evidence threshold.

## Acceptance criteria for the first release

- An analyst can ingest a document, open an entity dossier, and ask a question
  from the workbench.
- Every returned finding contains its statement, exact source quote, source
  identifier, confidence, and entailment score.
- A question without matching verified evidence produces no factual answer and
  creates a reviewable gap ticket.
- Current branch changes are validated against the repository's existing
  checks, and the as-built docs describe the shipped behavior.
