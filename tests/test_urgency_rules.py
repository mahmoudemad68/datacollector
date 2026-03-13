"""Tests for processors/urgency_rules.py."""
import pytest

from config.schema import Urgency
from processors.urgency_rules import UrgencyEngine


class TestEmergencySymptoms:
    def test_chest_pain_and_sob(self):
        eng = UrgencyEngine()
        result = eng.classify("Unknown condition", ["chest pain", "shortness of breath"])
        assert result == Urgency.EMERGENCY

    def test_anaphylaxis(self):
        eng = UrgencyEngine()
        result = eng.classify("Anaphylaxis", ["rash", "swelling"])
        assert result == Urgency.EMERGENCY

    def test_stroke_symptoms(self):
        eng = UrgencyEngine()
        result = eng.classify("Stroke", ["facial drooping", "arm weakness"])
        assert result == Urgency.EMERGENCY

    def test_sepsis_disease(self):
        eng = UrgencyEngine()
        result = eng.classify("Sepsis", ["fever", "rapid heart rate", "low blood pressure"])
        assert result == Urgency.EMERGENCY

    def test_acute_mi(self):
        eng = UrgencyEngine()
        result = eng.classify("Acute myocardial infarction", ["chest pain", "sweating"])
        assert result == Urgency.EMERGENCY

    def test_meningitis(self):
        eng = UrgencyEngine()
        result = eng.classify("Meningitis", ["severe headache", "stiff neck", "fever"])
        assert result == Urgency.EMERGENCY

    def test_loss_of_consciousness(self):
        eng = UrgencyEngine()
        result = eng.classify("Unknown", ["loss of consciousness", "confusion"])
        assert result == Urgency.EMERGENCY

    def test_cardiac_arrest(self):
        eng = UrgencyEngine()
        result = eng.classify("Cardiac arrest", ["unconscious"])
        assert result == Urgency.EMERGENCY


class TestHighSeverityDisease:
    def test_cancer_is_high(self):
        eng = UrgencyEngine()
        result = eng.classify("Lung cancer", ["persistent cough", "weight loss"])
        assert result == Urgency.HIGH

    def test_leukemia_is_high(self):
        eng = UrgencyEngine()
        result = eng.classify("Leukemia", ["fatigue", "easy bruising"])
        assert result == Urgency.HIGH

    def test_hiv_aids_is_high(self):
        eng = UrgencyEngine()
        result = eng.classify("HIV/AIDS", ["weight loss", "fatigue"])
        assert result == Urgency.HIGH

    def test_tuberculosis_is_high(self):
        eng = UrgencyEngine()
        result = eng.classify("Tuberculosis", ["chronic cough", "night sweats"])
        assert result == Urgency.HIGH

    def test_heart_failure_is_high(self):
        eng = UrgencyEngine()
        result = eng.classify("Heart failure", ["leg swelling", "fatigue"])
        assert result == Urgency.HIGH


class TestLowUrgencySymptoms:
    def test_common_cold(self):
        eng = UrgencyEngine()
        result = eng.classify("Common cold", ["runny nose", "sneezing"])
        assert result == Urgency.LOW

    def test_mild_rash(self):
        eng = UrgencyEngine()
        result = eng.classify("Minor rash", ["skin redness"])
        assert result == Urgency.LOW

    def test_insomnia(self):
        eng = UrgencyEngine()
        result = eng.classify("Insomnia", ["difficulty sleeping"])
        assert result == Urgency.LOW


class TestMediumUrgency:
    def test_diabetes(self):
        eng = UrgencyEngine()
        result = eng.classify("Type 2 diabetes mellitus", ["fatigue", "frequent urination"])
        assert result in (Urgency.MEDIUM, Urgency.HIGH)  # allowed either

    def test_asthma_mild(self):
        eng = UrgencyEngine()
        result = eng.classify("Asthma", ["wheezing", "mild cough"])
        assert result in (Urgency.MEDIUM, Urgency.HIGH)

    def test_pneumonia_medium_or_high(self):
        eng = UrgencyEngine()
        result = eng.classify("Pneumonia", ["cough", "fever"])
        assert result in (Urgency.MEDIUM, Urgency.HIGH, Urgency.EMERGENCY)

    def test_infection_returns_at_least_medium(self):
        eng = UrgencyEngine()
        result = eng.classify("Urinary tract infection", ["burning urination", "fever"])
        assert result in (Urgency.MEDIUM, Urgency.HIGH, Urgency.EMERGENCY)

    def test_urgency_enum_values(self):
        """All Urgency values should be valid enum members."""
        for val in Urgency:
            assert val in list(Urgency)
