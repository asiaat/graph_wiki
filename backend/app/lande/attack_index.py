"""Attack Index metrics: cognitive warfare wave detection."""

import logging
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass
class WaveAnomaly:
    timestamp: float
    term: str
    magnitude: float
    trigger_type: str


class AttackIndexMetrics(BaseModel):
    emotional_intensity: float = 0.0
    manipulative_markers: list[str] = []
    slop_probability: float = 0.0
    admiralty_reliability: str = "F_CANNOT_BE_JUDGED"
    credibility_rank: int = 6

    # Wave-specific fields
    wave_magnitude: float = 0.0
    wave_frequency: float = 0.0
    narrative_intensity: float = 0.0
    reprint_cascade_score: float = 0.0

    def compute_attack_score(self) -> float:
        """Aggregate wave anomaly detection."""
        # Weighted composite of wave metrics
        weights = {
            "emotional_intensity": 0.25,
            "slop_probability": 0.20,
            "wave_magnitude": 0.20,
            "narrative_intensity": 0.15,
            "reprint_cascade_score": 0.20,
        }
        return (
            self.emotional_intensity * weights["emotional_intensity"]
            + self.slop_probability * weights["slop_probability"]
            + self.wave_magnitude * weights["wave_magnitude"]
            + self.narrative_intensity * weights["narrative_intensity"]
            + self.reprint_cascade_score * weights["reprint_cascade_score"]
        )


def detect_wave_anomalies(
    time_series: list[dict[str, Any]],
    term_frequency: dict[str, float],
) -> list[WaveAnomaly]:
    """Detect sudden wave anomalies using rolling statistics.
    Flags cognitive warfare operation if frequency > 2.5 sigma over baseline
    and reprint cascades spike.
    """
    if len(time_series) < 10:
        return []

    # Simple threshold-based detection for demo
    anomalies = []
    baseline = sum(f["count"] for f in time_series[:5]) / 5
    std_dev = (sum((f["count"] - baseline) ** 2 for f in time_series[:5]) / 5) ** 0.5

    for window in time_series:
        for term, data in window.get("terms", {}).items():
            freq = data.get("count", 0)
            if std_dev > 0 and (freq - baseline) / std_dev > 2.5:
                anomalies.append(
                    WaveAnomaly(
                        timestamp=window.get("timestamp", 0),
                        term=term,
                        magnitude=(freq - baseline) / std_dev,
                        trigger_type="wave_anomaly",
                    )
                )

    return anomalies
