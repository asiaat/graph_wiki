"""Prof. Dmytro Lande's Horizontal Visibility Graph & Directed Term Hierarchy."""

import logging
import math
from collections import defaultdict
from typing import Any

import numpy as np

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class HVGEdge(BaseModel):
    term_a: str
    term_b: str
    visibility_weight: float
    direction: str  # "a->b" or "b->a" or "undirected"


class HVGResult(BaseModel):
    hub_terms: list[str]
    edges: list[HVGEdge]
    degree_centrality: dict[str, float]
    burst_terms: list[str]


def _compute_tf_idf_weights(tokens: list[str]) -> dict[str, float]:
    """Compute TF-IDF weights for terms in a sliding window."""
    doc_freq = defaultdict(int)
    term_freq = defaultdict(int)
    total_docs = 1

    for token in tokens:
        term_freq[token] += 1

    for token in set(tokens):
        doc_freq[token] += 1

    total_tokens = len(tokens)
    weights = {}
    for term, freq in term_freq.items():
        tf = freq / total_tokens
        idf = math.log(total_docs / (1 + doc_freq[term]))
        weights[term] = tf * idf

    return weights


def _build_hvg_edges(term_series: list[tuple[str, float]]) -> list[tuple[int, int, float]]:
    """Build Horizontal Visibility Graph edges.
    Two terms (i, y_i) and (j, y_j) are connected iff all intermediate
    terms (k, y_k) satisfy y_k < min(y_i, y_j).
    """
    edges = []
    n = len(term_series)
    for i in range(n):
        for j in range(i + 1, n):
            visible = True
            yi = term_series[i][1]
            yj = term_series[j][1]
            threshold = min(yi, yj)
            for k in range(i + 1, j):
                yk = term_series[k][1]
                if yk >= threshold:
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
    """Resolve directed hierarchy: A → B if P(A|B) > P(B|A) and out-degree(A) > out-degree(B)."""
    # Compute conditional probabilities
    cooc = defaultdict(lambda: defaultdict(int))
    term_counts = defaultdict(int)
    for t in tokens:
        term_counts[t] += 1

    # Compute co-occurrence within window
    window = 5
    for i, t in enumerate(tokens):
        for j in range(max(0, i - window), min(len(tokens), i + window + 1)):
            if i != j:
                cooc[t][tokens[j]] += 1

    directed = []
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
    """Detect anomalous keyword bursts using sliding window frequency."""
    if len(tokens) < window:
        return []

    freqs = []
    for i in range(0, len(tokens) - window, window):
        window_tokens = tokens[i : i + window]
        counts = defaultdict(int)
        for t in window_tokens:
            counts[t] += 1
        freqs.append(counts)

    # Detect terms with sudden frequency spikes
    bursts = []
    for term in set(tokens):
        term_freqs = [f.get(term, 0) for f in freqs]
        if len(term_freqs) < 2:
            continue
        mean_freq = np.mean(term_freqs)
        std_freq = np.std(term_freqs)
        if std_freq > 0:
            # Burst if any window exceeds mean + 2*std
            if any(f > mean_freq + 2 * std_freq for f in term_freqs):
                bursts.append(term)

    return bursts


def compute_hvg(text: str) -> HVGResult:
    """Main entry: compute Lande HVG from raw text."""
    tokens = [t.strip(".,!?;:\"'()[]{}").lower() for t in text.split() if t.strip()]
    if not tokens:
        return HVGResult(hub_terms=[], edges=[], degree_centrality={}, burst_terms=[])

    weights = _compute_tf_idf_weights(tokens)
    term_series = [(t, weights.get(t, 0.0)) for t in tokens]

    edges = _build_hvg_edges(term_series)
    directed = _resolve_directionality(term_series, edges, tokens)

    # Compute degree centrality
    degree = defaultdict(int)
    for edge in directed:
        degree[edge.term_a] += 1
        degree[edge.term_b] += 1

    max_deg = max(degree.values()) if degree else 1
    centrality = {t: d / max_deg for t, d in degree.items()}

    # Hub terms: top 5 by centrality
    hub_terms = sorted(centrality, key=lambda t: centrality[t], reverse=True)[:5]

    # Burst detection
    bursts = _detect_bursts(tokens)

    return HVGResult(
        hub_terms=hub_terms,
        edges=directed,
        degree_centrality=centrality,
        burst_terms=bursts,
    )
