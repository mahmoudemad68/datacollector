"""Rule-based urgency classification engine."""
from __future__ import annotations

import re
from typing import Any

from config.schema import Urgency

# ---------------------------------------------------------------------------
# Keyword sets
# ---------------------------------------------------------------------------

EMERGENCY_KEYWORDS: list[str] = [
    "chest pain", "shortness of breath", "difficulty breathing",
    "anaphylaxis", "anaphylactic", "cardiac arrest",
    "stroke", "facial drooping", "sudden weakness", "sudden numbness",
    "sudden confusion", "trouble speaking", "loss of consciousness",
    "unconscious", "seizure", "convulsion",
    "severe bleeding", "coughing up blood", "haemoptysis", "hemoptysis",
    "rapid heart rate", "low blood pressure", "septic shock",
    "high fever with stiff neck", "meningism",
    "acute myocardial infarction", "heart attack",
    "pulmonary embolism", "aortic dissection",
    "suicidal", "overdose",
]

HIGH_SEVERITY_DISEASES: set[str] = {
    "cancer", "leukemia", "lymphoma", "melanoma", "carcinoma",
    "sepsis", "septicemia", "bacteremia",
    "meningitis", "encephalitis",
    "heart failure", "coronary artery disease",
    "pulmonary fibrosis", "acute respiratory distress syndrome", "ards",
    "stroke", "transient ischemic attack", "tia",
    "hiv", "aids",
    "tuberculosis",
    "cirrhosis",
    "acute kidney injury",
    "pulmonary embolism",
    "deep vein thrombosis",
    "diabetic ketoacidosis",
    "hypertensive crisis",
    "eclampsia",
}

MEDIUM_SEVERITY_DISEASES: set[str] = {
    "diabetes", "hypertension",
    "asthma", "copd",
    "rheumatoid arthritis", "lupus",
    "inflammatory bowel disease", "crohn", "ulcerative colitis",
    "chronic kidney disease",
    "hypothyroidism", "hyperthyroidism",
    "depression", "bipolar disorder", "schizophrenia",
    "osteoporosis",
    "atrial fibrillation",
    "pneumonia",
    "hepatitis",
    "epilepsy",
    "parkinson", "alzheimer", "multiple sclerosis",
    "fibromyalgia",
    "anemia",
    "psoriasis",
}


# ---------------------------------------------------------------------------
# UrgencyEngine
# ---------------------------------------------------------------------------

class UrgencyEngine:
    """Classify the urgency level of a disease presentation.

    Rules are evaluated in order; the first matching rule wins.
    """

    def classify(
        self,
        disease_name: str,
        symptoms: list[str],
        meta: dict[str, Any] | None = None,
    ) -> Urgency:
        """Return an :class:`Urgency` enum value for the given presentation.

        Args:
            disease_name: Normalised disease name string.
            symptoms: List of symptom strings for this presentation.
            meta: Optional extra metadata (not currently used).

        Returns:
            One of :attr:`Urgency.EMERGENCY`, :attr:`Urgency.HIGH`,
            :attr:`Urgency.MEDIUM`, :attr:`Urgency.LOW`.
        """
        dn_lower = disease_name.lower()
        sym_lower = [s.lower() for s in symptoms]
        all_text = " ".join([dn_lower] + sym_lower)

        # ---- EMERGENCY ------------------------------------------------
        if self._check_emergency(dn_lower, sym_lower, all_text):
            return Urgency.EMERGENCY

        # ---- HIGH -----------------------------------------------------
        if self._check_high(dn_lower, sym_lower):
            return Urgency.HIGH

        # ---- MEDIUM ---------------------------------------------------
        if self._check_medium(dn_lower, sym_lower):
            return Urgency.MEDIUM

        # ---- LOW -------------------------------------------------------
        return Urgency.LOW

    # ------------------------------------------------------------------

    def _check_emergency(self, disease: str, symptoms: list[str], all_text: str) -> bool:
        # Direct keyword match in combined text
        for kw in EMERGENCY_KEYWORDS:
            if kw in all_text:
                return True

        # Specific dangerous combinations
        has_chest = any("chest" in s for s in symptoms)
        has_sob = any("breath" in s or "dyspnea" in s for s in symptoms)
        if has_chest and has_sob:
            return True

        # Known emergency disease names
        emergency_diseases = {
            "sepsis", "meningitis", "anaphylaxis",
            "acute myocardial infarction", "pulmonary embolism",
            "stroke", "aortic aneurysm", "diabetic ketoacidosis",
            "hypertensive emergency", "cardiac arrest",
        }
        for ed in emergency_diseases:
            if ed in disease:
                return True

        return False

    def _check_high(self, disease: str, symptoms: list[str]) -> bool:
        for pattern in HIGH_SEVERITY_DISEASES:
            if pattern in disease:
                return True

        # High fever
        for s in symptoms:
            if re.search(r"high fever|fever.*\d{3}|temperature.*\d{3}", s):
                return True

        # Bleeding symptoms
        if any("blood" in s and ("cough" in s or "vomit" in s or "stool" in s) for s in symptoms):
            return True

        return False

    def _check_medium(self, disease: str, symptoms: list[str]) -> bool:
        for pattern in MEDIUM_SEVERITY_DISEASES:
            if pattern in disease:
                return True

        # Moderate infection indicators
        moderate_syms = {"fever", "infection", "inflammation", "abscess"}
        if any(any(m in s for m in moderate_syms) for s in symptoms):
            return True

        return False
