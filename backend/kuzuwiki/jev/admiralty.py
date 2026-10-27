"""NATO Admiralty Code classifier: source reliability (A-F) + credibility (1-6).

The Admiralty system grades *sources* (reliability) separately from the
*information* they carry (credibility). This module implements a deterministic
classifier:

1. **Domain priors** - known publishers and official registries map to a
   baseline reliability class.
2. **Content signals** - attribution, numeric density and named official
   registers strengthen an unknown source; unattributed generalities weaken it.
3. **Corroboration** - a source already corroborated by independent documents in
   the graph moves up the credibility scale (1 = confirmed by others).

No network access and no LLM call, so it is reproducible and testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from kuzuwiki.jev.schemas import AdmiraltyReliability
from kuzuwiki.jev.textutil import sentence_split

#: (domain suffix or exact domain) -> reliability class
DOMAIN_PRIORS: dict[str, AdmiraltyReliability] = {
    # Primary / official registries
    ".gov": AdmiraltyReliability.A,
    ".mil": AdmiraltyReliability.A,
    ".int": AdmiraltyReliability.A,
    ".gov.uk": AdmiraltyReliability.A,
    "europa.eu": AdmiraltyReliability.A,
    "europarl.europa.eu": AdmiraltyReliability.A,
    "un.org": AdmiraltyReliability.A,
    "nato.int": AdmiraltyReliability.A,
    "imf.org": AdmiraltyReliability.A,
    "worldbank.org": AdmiraltyReliability.A,
    "registries": AdmiraltyReliability.A,
    # Established wire services
    "reuters.com": AdmiraltyReliability.A,
    "apnews.com": AdmiraltyReliability.A,
    "afp.com": AdmiraltyReliability.A,
    "bbc.co.uk": AdmiraltyReliability.A,
    "bbc.com": AdmiraltyReliability.A,
    "dpa.de": AdmiraltyReliability.B,
    "afp.com/en": AdmiraltyReliability.B,
    # Established outlets
    "nytimes.com": AdmiraltyReliability.B,
    "theguardian.com": AdmiraltyReliability.B,
    "ft.com": AdmiraltyReliability.B,
    "bloomberg.com": AdmiraltyReliability.B,
    "washingtonpost.com": AdmiraltyReliability.B,
    "economist.com": AdmiraltyReliability.B,
    "politico.eu": AdmiraltyReliability.B,
    "aljazeera.com": AdmiraltyReliability.C,
    "dw.com": AdmiraltyReliability.B,
    # Research institutes / think tanks
    "rand.org": AdmiraltyReliability.B,
    "csis.org": AdmiraltyReliability.B,
    "iiss.org": AdmiraltyReliability.B,
    "sipri.org": AdmiraltyReliability.B,
    "crsreports.congress.gov": AdmiraltyReliability.B,
    # Aggregators / user generated
    "medium.com": AdmiraltyReliability.D,
    "wordpress.com": AdmiraltyReliability.D,
    "blogspot.com": AdmiraltyReliability.D,
    "substack.com": AdmiraltyReliability.D,
    "wikipedia.org": AdmiraltyReliability.D,
    "reddit.com": AdmiraltyReliability.D,
    "quora.com": AdmiraltyReliability.D,
    "x.com": AdmiraltyReliability.E,
    "twitter.com": AdmiraltyReliability.E,
    "t.me": AdmiraltyReliability.E,
    "telegram.me": AdmiraltyReliability.E,
}

#: Domains that can never be rated better than this.
DOMAIN_CAPS: dict[str, AdmiraltyReliability] = {
    "medium.com": AdmiraltyReliability.D,
    "wordpress.com": AdmiraltyReliability.D,
    "blogspot.com": AdmiraltyReliability.D,
    "substack.com": AdmiraltyReliability.D,
    "wikipedia.org": AdmiraltyReliability.D,
    "reddit.com": AdmiraltyReliability.D,
    "quora.com": AdmiraltyReliability.D,
    "x.com": AdmiraltyReliability.E,
    "twitter.com": AdmiraltyReliability.E,
    "t.me": AdmiraltyReliability.E,
    "telegram.me": AdmiraltyReliability.E,
}

_RELIABILITY_ORDER = [
    AdmiraltyReliability.A,
    AdmiraltyReliability.B,
    AdmiraltyReliability.C,
    AdmiraltyReliability.D,
    AdmiraltyReliability.E,
    AdmiraltyReliability.F,
]

_OFFICIAL_MARKERS = (
    "according to",
    "the court",
    "the tribunal",
    "the ministry",
    "the agency",
    "official record",
    "public register",
    "filed with",
    "press release",
    "annual report",
    "audit",
    "sanctions list",
    "notice is hereby",
)

_ATTRIBUTION_RE = re.compile(
    r"\b(?:according to|reported by|said|told|confirmed by|announced by|stated that)\b", re.I
)
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")


@dataclass(frozen=True)
class AdmiraltyAssessment:
    reliability: AdmiraltyReliability
    credibility_rank: int
    rationale: str

    @property
    def reliability_letter(self) -> str:
        return self.reliability.value[0]


def _domain_match(domain: str) -> AdmiraltyReliability | None:
    d = domain.strip().lower()
    if d.startswith("http"):
        d = re.sub(r"^https?://", "", d).split("/")[0]
    if not d:
        return None
    if d in DOMAIN_PRIORS:
        return DOMAIN_PRIORS[d]
    # Longest suffix match wins (en.europa.eu before .eu style collisions).
    for suffix, prior in sorted(DOMAIN_PRIORS.items(), key=lambda kv: -len(kv[0])):
        if d.endswith(suffix):
            return prior
    for tld in (".gov", ".mil", ".int"):
        if d.endswith(tld):
            return DOMAIN_PRIORS[tld]
    return None


def _cap_reliability(domain: str, candidate: AdmiraltyReliability) -> AdmiraltyReliability:
    cap = None
    d = domain.strip().lower()
    for known, ceiling in DOMAIN_CAPS.items():
        if d == known or d.endswith("." + known) or d.endswith(known):
            cap = ceiling
            break
    if cap is None:
        return candidate
    return max(candidate, cap, key=lambda r: _RELIABILITY_ORDER.index(r))


def classify_source(
    text: str,
    domain: str | None = None,
    corroborations: int = 0,
) -> AdmiraltyAssessment:
    """Assign an Admiralty rating to a source document."""
    domain = domain or ""
    prior = _domain_match(domain)
    sentences = sentence_split(text or "")

    attributed = bool(_ATTRIBUTION_RE.search(text or ""))
    official = any(m in (text or "").lower() for m in _OFFICIAL_MARKERS)
    numbers = len(_NUMBER_RE.findall(text or ""))
    density = numbers / max(len(sentences), 1)

    if prior is not None:
        reliability = prior
        rationale = f"domain prior for '{domain}'"
    else:
        # Unknown source: lean on the content signals.
        if official and attributed:
            reliability = AdmiraltyReliability.C
            rationale = "unknown domain but officially attributed and numeric"
        elif attributed or density > 2.0:
            reliability = AdmiraltyReliability.D
            rationale = "unknown domain, limited attribution"
        elif sentences and len(sentences) < 3:
            reliability = AdmiraltyReliability.E
            rationale = "unknown domain, short unattributed content"
        else:
            reliability = AdmiraltyReliability.F
            rationale = "unknown domain, no reliability signals"

    reliability = _cap_reliability(domain, reliability)

    # Credibility 1-6: the information itself, corroborated or not.
    if corroborations >= 2:
        rank = 1
    elif corroborations == 1:
        rank = 2
    elif reliability in (AdmiraltyReliability.A, AdmiraltyReliability.B):
        rank = 3
    elif reliability == AdmiraltyReliability.C:
        rank = 4
    elif reliability in (AdmiraltyReliability.D, AdmiraltyReliability.E):
        rank = 5
    else:
        rank = 6

    return AdmiraltyAssessment(reliability=reliability, credibility_rank=rank, rationale=rationale)
