"""Probability computation engine for disease-symptom relations."""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# Common symptoms that appear across many diseases get a higher fallback probability
_COMMON_SYMPTOMS = {
    "fatigue", "fever", "headache", "nausea", "vomiting", "pain",
    "cough", "shortness of breath", "dizziness", "weakness",
}

# Relatively specific symptoms get a lower fallback probability
_SPECIFIC_SYMPTOMS = {
    "hemoptysis", "coughing up blood", "seizures", "hallucinations",
    "delusions", "paralysis", "coma", "rash", "jaundice",
}


class ProbabilityEngine:
    """Computes weighted probabilities for disease-symptom relationships.

    Multiple data sources (Infermedica, SymCAT, HDSN) may report a
    frequency/weight for the same (disease, symptom) pair.  This engine
    reconciles them into a single probability value using configurable
    per-source weights.
    """

    DEFAULT_WEIGHTS: dict[str, float] = {
        "infermedica": 0.40,
        "symcat": 0.35,
        "hdsn": 0.25,
    }

    def __init__(self, source_weights: dict[str, float] | None = None) -> None:
        self.source_weights: dict[str, float] = source_weights or dict(self.DEFAULT_WEIGHTS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(
        self, disease_symptom_relations: list[dict[str, Any]]
    ) -> dict[tuple[str, str], float]:
        """Compute final probabilities for every (disease_id, symptom_name) pair.

        Args:
            disease_symptom_relations: List of relation dicts, each containing
                at minimum ``disease_id``, ``symptom_name``, ``weight`` (or
                ``frequency`` / ``co_occurrence_score``), and ``source``.

        Returns:
            ``{(disease_id, symptom_name): probability}``
        """
        # Group by (disease_id, symptom_name)
        groups: dict[tuple[str, str], list[tuple[float, float]]] = {}
        for rel in disease_symptom_relations:
            did = rel.get("disease_id", rel.get("disease_name", "unknown"))
            sym = rel.get("symptom_name", "")
            if not did or not sym:
                continue
            key = (did, sym)
            value = float(
                rel.get("weight", rel.get("frequency", rel.get("co_occurrence_score", 0.5)))
            )
            source = rel.get("source", "unknown")
            weight = self.source_weights.get(source, 0.1)
            groups.setdefault(key, []).append((value, weight))

        result: dict[tuple[str, str], float] = {}
        for key, vw_pairs in groups.items():
            result[key] = self._weighted_average(vw_pairs)
        return result

    def enrich_relations(self, relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Add a ``probability`` field to each relation dict in-place.

        Relations that already carry a numeric probability are left unchanged.
        """
        probability_map = self.compute(relations)
        enriched: list[dict[str, Any]] = []
        for rel in relations:
            r = dict(rel)
            did = r.get("disease_id", r.get("disease_name", "unknown"))
            sym = r.get("symptom_name", "")
            key = (did, sym)
            if "probability" not in r:
                r["probability"] = probability_map.get(key, self._fallback_probability(did, sym))
            enriched.append(r)
        return enriched

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _weighted_average(values_weights: list[tuple[float, float]]) -> float:
        """Return the weighted mean of (value, weight) pairs, clamped to [0, 1]."""
        if not values_weights:
            return 0.5
        total_weight = sum(w for _, w in values_weights)
        if total_weight == 0:
            return sum(v for v, _ in values_weights) / len(values_weights)
        result = sum(v * w for v, w in values_weights) / total_weight
        return max(0.0, min(1.0, result))

    def _fallback_probability(self, disease_name: str, symptom_name: str) -> float:
        """Heuristic probability when no source data is available."""
        sym_lower = symptom_name.lower()
        if any(s in sym_lower for s in _COMMON_SYMPTOMS):
            return 0.55
        if any(s in sym_lower for s in _SPECIFIC_SYMPTOMS):
            return 0.30
        # Base probability via hash-stable pseudo-random spread
        seed = abs(hash(f"{disease_name}:{symptom_name}")) % 1000
        # Spread between 0.30 and 0.75
        return round(0.30 + (seed / 1000) * 0.45, 3)
