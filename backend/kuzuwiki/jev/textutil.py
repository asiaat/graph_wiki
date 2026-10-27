"""Shared text normalisation helpers for the JEV pipeline.

Kept deliberately small and dependency-free so the slop classifier, the HVG
builder and the entailment gate all agree on what a "token" is.
"""

from __future__ import annotations

import re

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-\.]*")

#: Generic English stopwords. Domain packs layer their own on top of this.
STOPWORDS: frozenset[str] = frozenset(
    """
    a an the and or but if then than that this these those there here of in on at by for with
    from to into over under about after before during between during it its it's is are was
    were be been being has have had do does did not no nor so such as we they them their he
    she his her you your i our us me my mine ours which who whom whose what when where why
    how all any both each few more most other some only own same too very can will just
    should now also may might must would could per via using used use new old one two three
    first second last next previous said says say according reported report reports
    """.split()
)

_SUFFIXES = ("ing", "ed", "es", "s", "ly", "ment", "ions", "ion", "ers", "er")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, punctuation stripped."""
    if not text:
        return []
    return [m.group(0).lower().strip(".'-") for m in TOKEN_RE.finditer(text)]


def stem(token: str) -> str:
    """Very small suffix stripper - enough to align ``manufactures``/``manufacturing``."""
    if len(token) <= 4:
        return token
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def content_tokens(text: str, extra_stopwords: frozenset[str] | set[str] | None = None) -> set[str]:
    """Token set with stopwords and single characters removed."""
    stops = STOPWORDS | set(extra_stopwords or ())
    return {t for t in tokenize(text) if t not in stops and len(t) > 1}


def stemmed_tokens(text: str, extra_stopwords: frozenset[str] | set[str] | None = None) -> set[str]:
    """Content tokens reduced to their stems."""
    return {stem(t) for t in content_tokens(text, extra_stopwords)}


def sentence_split(text: str) -> list[str]:
    """Split on sentence terminators, keeping non-empty sentences."""
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    return [p.strip() for p in parts if p and p.strip()]
