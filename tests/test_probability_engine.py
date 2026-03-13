"""Tests for processors/probability_engine.py."""
import pytest

from processors.probability_engine import ProbabilityEngine


class TestWeightedAverage:
    def test_single_value(self):
        eng = ProbabilityEngine()
        assert eng._weighted_average([(0.8, 1.0)]) == pytest.approx(0.8)

    def test_equal_weights(self):
        eng = ProbabilityEngine()
        result = eng._weighted_average([(0.4, 1.0), (0.6, 1.0)])
        assert result == pytest.approx(0.5)

    def test_higher_weight_dominates(self):
        eng = ProbabilityEngine()
        # weight=3 on 0.9, weight=1 on 0.1
        result = eng._weighted_average([(0.9, 3.0), (0.1, 1.0)])
        assert result > 0.5  # should be closer to 0.9

    def test_empty_returns_0_5(self):
        eng = ProbabilityEngine()
        assert eng._weighted_average([]) == pytest.approx(0.5)

    def test_clamps_to_0_1(self):
        eng = ProbabilityEngine()
        # Very high values should be clamped
        result = eng._weighted_average([(2.0, 1.0)])
        assert result <= 1.0

    def test_zero_weight_falls_back_to_mean(self):
        eng = ProbabilityEngine()
        result = eng._weighted_average([(0.6, 0.0), (0.4, 0.0)])
        assert result == pytest.approx(0.5)


class TestComputeProbabilities:
    def _make_relations(self):
        return [
            {"disease_id": "D1", "symptom_name": "fever", "weight": 0.8, "source": "infermedica"},
            {"disease_id": "D1", "symptom_name": "fever", "weight": 0.7, "source": "symcat"},
            {"disease_id": "D1", "symptom_name": "cough", "weight": 0.6, "source": "infermedica"},
            {"disease_id": "D2", "symptom_name": "rash", "weight": 0.5, "source": "hdsn"},
        ]

    def test_returns_dict(self):
        eng = ProbabilityEngine()
        result = eng.compute(self._make_relations())
        assert isinstance(result, dict)

    def test_keys_are_tuples(self):
        eng = ProbabilityEngine()
        result = eng.compute(self._make_relations())
        for key in result:
            assert isinstance(key, tuple)
            assert len(key) == 2

    def test_values_in_0_1(self):
        eng = ProbabilityEngine()
        result = eng.compute(self._make_relations())
        for val in result.values():
            assert 0.0 <= val <= 1.0

    def test_multiple_sources_averaged(self):
        eng = ProbabilityEngine()
        result = eng.compute(self._make_relations())
        # D1-fever should be between 0.7 and 0.8
        fever_prob = result.get(("D1", "fever"), None)
        assert fever_prob is not None
        assert 0.65 <= fever_prob <= 0.85

    def test_empty_input(self):
        eng = ProbabilityEngine()
        assert eng.compute([]) == {}

    def test_skips_missing_disease_id(self):
        eng = ProbabilityEngine()
        relations = [{"symptom_name": "fever", "weight": 0.5, "source": "symcat"}]
        result = eng.compute(relations)
        # Should handle gracefully (may use empty-string key or skip)
        assert isinstance(result, dict)

    def test_custom_source_weights(self):
        eng = ProbabilityEngine(source_weights={"infermedica": 1.0, "symcat": 0.0})
        relations = [
            {"disease_id": "D1", "symptom_name": "cough", "weight": 0.9, "source": "infermedica"},
            {"disease_id": "D1", "symptom_name": "cough", "weight": 0.1, "source": "symcat"},
        ]
        result = eng.compute(relations)
        # With symcat weight=0, result should be close to 0.9
        cough_prob = result[("D1", "cough")]
        assert cough_prob > 0.5


class TestFallbackProbability:
    def test_in_range(self):
        eng = ProbabilityEngine()
        p = eng._fallback_probability("Diabetes", "fatigue")
        assert 0.0 <= p <= 1.0

    def test_common_symptom_higher(self):
        eng = ProbabilityEngine()
        p_common = eng._fallback_probability("SomeDisease", "fatigue")
        p_specific = eng._fallback_probability("SomeDisease", "hemoptysis")
        assert p_common >= p_specific

    def test_deterministic(self):
        eng = ProbabilityEngine()
        p1 = eng._fallback_probability("Flu", "fever")
        p2 = eng._fallback_probability("Flu", "fever")
        assert p1 == p2


class TestEnrichRelations:
    def test_adds_probability_field(self):
        eng = ProbabilityEngine()
        relations = [
            {"disease_id": "D1", "symptom_name": "fever", "weight": 0.8, "source": "infermedica"},
        ]
        enriched = eng.enrich_relations(relations)
        assert all("probability" in r for r in enriched)

    def test_does_not_overwrite_existing_probability(self):
        eng = ProbabilityEngine()
        relations = [
            {"disease_id": "D1", "symptom_name": "cough",
             "weight": 0.8, "source": "infermedica", "probability": 0.42},
        ]
        enriched = eng.enrich_relations(relations)
        assert enriched[0]["probability"] == pytest.approx(0.42)

    def test_probabilities_in_range(self):
        eng = ProbabilityEngine()
        relations = [
            {"disease_id": f"D{i}", "symptom_name": "fever",
             "weight": 0.5, "source": "symcat"}
            for i in range(20)
        ]
        enriched = eng.enrich_relations(relations)
        for r in enriched:
            assert 0.0 <= r["probability"] <= 1.0
