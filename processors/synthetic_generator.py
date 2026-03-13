"""Synthetic medical record generator."""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime
from typing import Any

from config.schema import AgeGroup, Gender, Urgency
from config.settings import settings

logger = logging.getLogger(__name__)

_AGE_GROUPS = list(AgeGroup)
_GENDERS = list(Gender)


class SyntheticGenerator:
    """Generate synthetic :class:`~config.schema.MedicalRecord`-compatible dicts.

    The generator samples symptoms from a disease-symptom probability map,
    assigns demographics randomly, and enriches records with treatment and
    urgency information.
    """

    def __init__(
        self,
        disease_symptom_map: dict[str, dict],
        probability_map: dict[tuple[str, str], float],
        urgency_engine: Any,
        treatment_map: dict[str, list[str]],
        drug_map: dict[str, list[dict]],
    ) -> None:
        """
        Args:
            disease_symptom_map: ``{disease_id: {"disease_name": str,
                "symptoms": [{"name": str, "probability": float}]}}``
            probability_map: ``{(disease_id, symptom_name): probability}``
            urgency_engine: Instance with ``classify(disease_name, symptoms)``
            treatment_map: ``{disease_name: [treatment_str, ...]}``
            drug_map: ``{disease_name: [{"name": str, "dose": str|None, "route": str|None}]}``
        """
        self.disease_symptom_map = disease_symptom_map
        self.probability_map = probability_map
        self.urgency_engine = urgency_engine
        self.treatment_map = treatment_map
        self.drug_map = drug_map

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_record(
        self,
        disease_id: str,
        age_group: AgeGroup | None = None,
        gender: Gender | None = None,
    ) -> dict:
        """Generate a single synthetic medical record dict.

        Args:
            disease_id: Key into :attr:`disease_symptom_map`.
            age_group: Override age group; picked randomly if ``None``.
            gender: Override gender; picked randomly if ``None``.

        Returns:
            A dict compatible with :class:`~config.schema.MedicalRecord`.
        """
        disease_info = self.disease_symptom_map.get(disease_id, {})
        disease_name = disease_info.get("disease_name", disease_id)
        symptom_pool = disease_info.get("symptoms", [])

        # Sample symptoms using weighted probabilities
        selected_symptoms = self._sample_symptoms(symptom_pool)

        # Compute aggregate probability
        prob_values = [
            self.probability_map.get((disease_id, s), 0.5)
            for s in selected_symptoms
        ]
        probability = round(sum(prob_values) / max(len(prob_values), 1), 4)

        # Demographics
        ag = age_group or random.choice(_AGE_GROUPS)
        gd = gender or random.choice(_GENDERS)

        # Urgency
        urgency: Urgency = self.urgency_engine.classify(disease_name, selected_symptoms)

        # Treatments and drugs
        treatments = list(self.treatment_map.get(disease_name, []))
        drugs = list(self.drug_map.get(disease_name, []))

        return {
            "record_id": str(uuid.uuid4()),
            "disease_id": disease_id,
            "disease_name": disease_name,
            "symptoms": selected_symptoms,
            "age_group": ag.value if isinstance(ag, AgeGroup) else ag,
            "gender": gd.value if isinstance(gd, Gender) else gd,
            "probability": probability,
            "treatment": treatments,
            "drugs": drugs,
            "urgency": urgency.value if isinstance(urgency, Urgency) else urgency,
            "source_list": ["synthetic"],
            "confidence_score": round(random.uniform(0.55, 0.95), 3),
            "is_synthetic": True,
            "created_at": datetime.utcnow().isoformat(),
            "meta": {"generator_version": "1.0"},
        }

    def generate_batch(
        self,
        disease_ids: list[str],
        count: int,
        existing_count: int,
        target_total: int,
    ) -> list[dict]:
        """Generate up to *count* synthetic records respecting the synthetic cap.

        Args:
            disease_ids: Disease IDs to distribute records across.
            count: Maximum number of records to generate in this batch.
            existing_count: Number of real records already in the dataset.
            target_total: Overall target dataset size.

        Returns:
            List of record dicts.
        """
        if not disease_ids:
            logger.warning("generate_batch: disease_ids is empty")
            return []

        # Enforce synthetic cap
        max_synthetic = int(target_total * settings.SYNTHETIC_CAP)
        # existing_count here refers to existing *synthetic* records (or total)
        # We use a conservative approach: cap total synthetic at SYNTHETIC_CAP * target
        remaining_cap = max(0, max_synthetic - existing_count)
        actual_count = min(count, remaining_cap)

        if actual_count <= 0:
            logger.info("Synthetic cap reached – skipping batch generation")
            return []

        records: list[dict] = []
        per_disease = max(1, actual_count // len(disease_ids))
        extra = actual_count - per_disease * len(disease_ids)

        for i, did in enumerate(disease_ids):
            batch_size = per_disease + (1 if i < extra else 0)
            for _ in range(batch_size):
                rec = self.generate_record(did)
                if self._avoid_anomalous(rec["symptoms"]):
                    records.append(rec)
                if len(records) >= actual_count:
                    break
            if len(records) >= actual_count:
                break

        return records

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _sample_symptoms(self, symptom_pool: list[dict]) -> list[str]:
        """Sample symptoms via weighted Bernoulli draws.

        Each symptom's probability acts as the independent draw probability.
        The result is clamped to [SYMPTOM_MIN, SYMPTOM_MAX].
        """
        if not symptom_pool:
            return []

        selected = []
        for sym in symptom_pool:
            name = sym.get("name", "")
            prob = float(sym.get("probability", 0.5))
            if name and random.random() < prob:
                selected.append(name)

        # Enforce minimum
        if len(selected) < settings.SYMPTOM_MIN:
            pool_copy = [s["name"] for s in symptom_pool if s.get("name") and s["name"] not in selected]
            random.shuffle(pool_copy)
            need = settings.SYMPTOM_MIN - len(selected)
            selected.extend(pool_copy[:need])

        # Enforce maximum
        if len(selected) > settings.SYMPTOM_MAX:
            selected = random.sample(selected, settings.SYMPTOM_MAX)

        return selected

    def _avoid_anomalous(self, symptoms: list[str]) -> bool:
        """Return True if the symptom combination appears plausible.

        Filters out anatomically impossible or contradictory combinations.
        """
        sym_lower = {s.lower() for s in symptoms}

        # Flag implausible contradictions
        contradictions = [
            ({"diarrhea", "constipation"}, lambda s: "diarrhea" in s and "constipation" in s),
        ]
        for _, check in contradictions:
            if check(sym_lower):
                return False

        return True
