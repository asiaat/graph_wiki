"""Prof. Dmytro Lande's Horizontal Visibility Graph & directed term hierarchy.

The HVG turns a *sequence* of weighted terms into a graph: two terms at
positions ``i`` and ``j`` are connected iff every intermediate term is
lighter than both of them::

    w(t_k) < min(w(t_i), w(t_j))   for all k in (i, j)

That rule alone extracts a scale-free backbone and, with the conditional
probability asymmetry, a natural hierarchy of terms.

Two practical corrections over the first implementation:

* **Stopwords are removed before the graph is built.** Otherwise the hub terms
  come back as ``['the', 'unit', 'and']`` - the domain packs already declare
  the stopword list, it just was never loaded.
* **The weight is smooth TF-IDF, not a degenerate one.** With a single
  document the classic IDF is ``log(1/(1+df))``, which is *negative* and
  inverts the notion of prominence. Smoothed IDF keeps the ordering sane.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from collections.abc import Iterable

from pydantic import BaseModel

from kuzuwiki.jev.textutil import STOPWORDS

logger = logging.getLogger(__name__)

#: Sliding window (in tokens) used when building visibility edges. A full
#: O(n^2) sweep is quadratic in document length and unusable for long
#: documents; the visibility rule is local in practice.
DEFAULT_WINDOW = 64


class HVGEdge(BaseModel):
    term_a: str
    term_b: str
    visibility_weight: float
    direction: str  # "a->b", "b->a" or "undirected"


class HVGResult(BaseModel):
    hub_terms: list[str]
    edges: list[HVGEdge]
    degree_centrality: dict[str, float]
    burst_terms: list[str]
    term_weights: dict[str, float] = {}


def _compute_tf_idf_weights(tokens: list[str]) -> dict[str, float]:
    """Smoothed TF-IDF prominence weights for a single document.

    ``idf = log((1 + N) / (1 + df)) + 1`` with ``N = 1`` yields ``idf = 1``
    for every term, so the weight degenerates to term frequency - which is the
    correct prominence signal for a single document and, unlike the naive
    formula, is never negative.
    """
    term_freq: dict[str, int] = defaultdict(int)
    for token in tokens:
        term_freq[token] += 1

    total_tokens = len(tokens)
    total_docs = 1
    weights: dict[str, float] = {}
    for term, freq in term_freq.items():
        tf = freq / total_tokens
        df = 1  # the term occurs in this (only) document
        idf = math.log((1 + total_docs) / (1 + df)) + 1.0
        weights[term] = tf * idf
    return weights


def _build_hvg_edges(
    term_series: list[tuple[str, float]], window: int = DEFAULT_WINDOW
) -> list[tuple[int, int, float]]:
    """Build Horizontal Visibility Graph edges.

    Two terms ``(i, w_i)`` and ``(j, w_j)`` are connected iff all
    intermediate terms satisfy ``w_k < min(w_i, w_j)``.
    """
    edges: list[tuple[int, int, float]] = []
    n = len(term_series)
    for i in range(n):
        wi = term_series[i][1]
        for j in range(i + 1, min(n, i + window + 1)):
            wj = term_series[j][1]
            threshold = min(wi, wj)
            visible = True
            for k in range(i + 1, j):
                if term_series[k][1] >= threshold:
                    visible = False
                    break
            if visible:
                edges.append((i, j, threshold))
    return edges


def _resolve_directionality(
    term_series: list[tuple[str, float]],
    edges: list[tuple[int, int, float]],
    tokens: list[str],
) -> list[HVGEdge]:
    """Orient the edges: ``A -> B`` when ``P(A|B) > P(B|A)``.

    The general term (the hub) points at the specific term.
    """
    term_counts: dict[str, int] = defaultdict(int)
    for token in tokens:
        term_counts[token] += 1

    cooc: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    window = 5
    for i, token in enumerate(tokens):
        for j in range(max(0, i - window), min(len(tokens), i + window + 1)):
            if i != j:
                cooc[token][tokens[j]] += 1

    degree: dict[str, int] = defaultdict(int)
    for i, j, _ in edges:
        degree[term_series[i][0]] += 1
        degree[term_series[j][0]] += 1

    directed: list[HVGEdge] = []
    for i, j, weight in edges:
        term_i = term_series[i][0]
        term_j = term_series[j][0]
        p_ij = cooc[term_i][term_j] / max(term_counts[term_j], 1)
        p_ji = cooc[term_j][term_i] / max(term_counts[term_i], 1)

        if p_ij > p_ji:
            direction = f"{term_i}->{term_j}"
        elif p_ji > p_ij:
            direction = f"{term_j}->{term_i}"
        else:
            direction = "undirected"

        directed.append(
            HVGEdge(
                term_a=term_i,
                term_b=term_j,
                visibility_weight=weight,
                direction=direction,
            )
        )
    return directed


def _detect_bursts(tokens: list[str], window: int = 50) -> list[str]:
    """Detect anomalous keyword bursts using a sliding window frequency."""
    if len(tokens) < window * 2:
        return []

    freqs: list[dict[str, int]] = []
    for i in range(0, len(tokens) - window, window):
        counts: dict[str, int] = defaultdict(int)
        for token in tokens[i : i + window]:
            counts[token] += 1
        freqs.append(counts)

    bursts: list[str] = []
    for term in set(tokens):
        series = [f.get(term, 0) for f in freqs]
        if len(series) < 2:
            continue
        mean = sum(series) / len(series)
        variance = sum((v - mean) ** 2 for v in series) / len(series)
        std = variance**0.5
        if std > 0 and any(v > mean + 2 * std for v in series):
            bursts.append(term)
    return bursts


def compute_hvg(
    text: str,
    stopwords: Iterable[str] | None = None,
    window: int = DEFAULT_WINDOW,
) -> HVGResult:
    """Compute the Lande HVG for a document.

    ``stopwords`` overrides the domain stopword list; when omitted the
    domain packs are consulted.
    """
    from kuzuwiki.lande.domain_schema import default_stopwords

    if stopwords is None:
        stop_set = default_stopwords()
    else:
        stop_set = {str(w).lower() for w in stopwords}

    tokens = [t.strip(".,!?;:\"'()[]{}").lower() for t in text.split() if t.strip()]
    # Stopwords never become nodes in the visibility graph.
    tokens = [t for t in tokens if t not in stop_set and t not in STOPWORDS and len(t) > 1]

    if not tokens:
        return HVGResult(hub_terms=[], edges=[], degree_centrality={}, burst_terms=[])

    weights = _compute_tf_idf_weights(tokens)
    term_series = [(t, weights.get(t, 0.0)) for t in tokens]

    edges = _build_hvg_edges(term_series, window=window)
    directed = _resolve_directionality(term_series, edges, tokens)

    degree: dict[str, int] = defaultdict(int)
    for edge in directed:
        degree[edge.term_a] += 1
        degree[edge.term_b] += 1

    max_deg = max(degree.values()) if degree else 1
    centrality = {t: d / max_deg for t, d in degree.items()}

    hub_terms = sorted(centrality, key=lambda t: centrality[t], reverse=True)[:5]
    bursts = _detect_bursts(tokens)

    return HVGResult(
        hub_terms=hub_terms,
        edges=directed,
        degree_centrality=centrality,
        burst_terms=bursts,
        term_weights={t: round(weights.get(t, 0.0), 6) for t in centrality},
    )
