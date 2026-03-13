"""Tests for processors/normalization.py."""
import pytest

from processors.normalization import (
    build_symptom_ontology,
    deduplicate_by_key,
    merge_synonyms,
    normalize_disease_name,
    normalize_symptom_name,
    normalize_text,
)


class TestNormalizeText:
    def test_lowercases(self):
        assert normalize_text("FEVER") == "fever"

    def test_strips_whitespace(self):
        assert normalize_text("  headache  ") == "headache"

    def test_collapses_internal_spaces(self):
        assert normalize_text("chest   pain") == "chest pain"

    def test_handles_empty_string(self):
        assert normalize_text("") == ""

    def test_removes_special_chars(self):
        result = normalize_text("fever! @#$%")
        assert "!" not in result
        assert "@" not in result

    def test_preserves_hyphens(self):
        result = normalize_text("non-hodgkin lymphoma")
        assert "non-hodgkin" in result

    def test_normalises_unicode(self):
        # accented characters should be transliterated or stripped
        result = normalize_text("Hépatite")
        assert isinstance(result, str)
        assert len(result) > 0


class TestNormalizeDiseaseName:
    def test_comma_inversion(self):
        result = normalize_disease_name("Diabetes, Type 2")
        assert "diabetes" in result
        assert "type 2" in result
        # Should be "type 2 diabetes" not "diabetes type 2"
        assert result.index("type") < result.index("diabetes")

    def test_no_comma(self):
        result = normalize_disease_name("Tuberculosis")
        assert result == "tuberculosis"

    def test_empty_string(self):
        assert normalize_disease_name("") == ""

    def test_handles_rheumatoid_arthritis(self):
        result = normalize_disease_name("Arthritis, Rheumatoid")
        assert "rheumatoid" in result
        assert "arthritis" in result

    def test_lowercase_output(self):
        result = normalize_disease_name("Type 2 Diabetes Mellitus")
        assert result == result.lower()


class TestDeduplicateByKey:
    def test_removes_exact_duplicates(self):
        records = [
            {"id": "a", "val": 1},
            {"id": "b", "val": 2},
            {"id": "a", "val": 3},  # duplicate
        ]
        result = deduplicate_by_key(records, "id")
        assert len(result) == 2
        ids = [r["id"] for r in result]
        assert ids.count("a") == 1

    def test_keeps_first_occurrence(self):
        records = [
            {"id": "x", "val": 10},
            {"id": "x", "val": 99},
        ]
        result = deduplicate_by_key(records, "id")
        assert result[0]["val"] == 10

    def test_empty_list(self):
        assert deduplicate_by_key([], "id") == []

    def test_no_duplicates(self):
        records = [{"id": str(i)} for i in range(5)]
        result = deduplicate_by_key(records, "id")
        assert len(result) == 5

    def test_missing_key_treated_as_none(self):
        records = [{"name": "a"}, {"name": "b"}, {"other": "x"}]
        result = deduplicate_by_key(records, "id")
        # All records have no 'id' → same key (None), deduplicated to 1
        assert len(result) == 1


class TestMergeSynonyms:
    def test_merges_same_disease(self):
        records = [
            {"disease_name": "Influenza", "synonyms": ["flu"], "disease_id": "d1"},
            {"disease_name": "Influenza", "synonyms": ["grippe"], "disease_id": "d1"},
        ]
        merged = merge_synonyms(records)
        key = "influenza"
        assert key in merged
        assert "flu" in merged[key]["synonyms"]
        assert "grippe" in merged[key]["synonyms"]

    def test_deduplicates_synonyms(self):
        records = [
            {"disease_name": "Flu", "synonyms": ["influenza"], "disease_id": "d1"},
            {"disease_name": "Flu", "synonyms": ["influenza"], "disease_id": "d1"},
        ]
        merged = merge_synonyms(records)
        key = "flu"
        assert merged[key]["synonyms"].count("influenza") == 1

    def test_different_diseases_separate(self):
        records = [
            {"disease_name": "Flu", "synonyms": [], "disease_id": "d1"},
            {"disease_name": "Cold", "synonyms": [], "disease_id": "d2"},
        ]
        merged = merge_synonyms(records)
        assert len(merged) == 2

    def test_empty_list(self):
        assert merge_synonyms([]) == {}


class TestBuildSymptomOntology:
    def test_basic_mapping(self):
        variants = [["headache", "head pain", "cephalalgia"]]
        ontology = build_symptom_ontology(variants)
        # All variants map to the shortest one
        assert "headache" in ontology
        assert "head pain" in ontology

    def test_empty_input(self):
        assert build_symptom_ontology([]) == {}

    def test_canonical_is_shortest(self):
        variants = [["shortness of breath", "dyspnea", "breathlessness"]]
        ontology = build_symptom_ontology(variants)
        # canonical should be "dyspnea" (shortest)
        canonical = ontology.get("dyspnea")
        assert canonical == "dyspnea"

    def test_ignores_empty_variants(self):
        variants = [["", "  ", "fever"]]
        ontology = build_symptom_ontology(variants)
        assert "" not in ontology
