"""Tests for config/schema.py."""
import pytest
from datetime import datetime

from config.schema import (
    AgeGroup,
    DrugInfo,
    Gender,
    MedicalRecord,
    Urgency,
    record_to_dict,
    validate_record,
)


def _valid_record_dict(**overrides) -> dict:
    base = {
        "record_id": "test-uuid-1234",
        "disease_id": "icd-1A00",
        "disease_name": "Cholera",
        "symptoms": ["diarrhoea", "vomiting", "dehydration"],
        "age_group": "adult",
        "gender": "male",
        "probability": 0.8,
        "urgency": "high",
    }
    base.update(overrides)
    return base


class TestValidRecordCreation:
    def test_minimal_valid_record(self):
        data = _valid_record_dict()
        record = MedicalRecord.model_validate(data)
        assert record.disease_name == "Cholera"
        assert record.age_group == AgeGroup.ADULT
        assert record.gender == Gender.MALE
        assert record.urgency == Urgency.HIGH
        assert len(record.symptoms) == 3

    def test_default_fields_populated(self):
        data = _valid_record_dict()
        record = MedicalRecord.model_validate(data)
        assert record.is_synthetic is False
        assert 0.0 <= record.confidence_score <= 1.0
        assert isinstance(record.created_at, datetime)
        assert record.treatment == []
        assert record.drugs == []

    def test_full_record_with_drugs(self):
        data = _valid_record_dict(
            drugs=[{"name": "ORS", "dose": "1L/hr", "route": "oral"}],
            treatment=["oral rehydration therapy"],
            source_list=["icd11"],
            is_synthetic=True,
        )
        record = MedicalRecord.model_validate(data)
        assert len(record.drugs) == 1
        assert record.drugs[0].name == "ORS"
        assert record.is_synthetic is True


class TestInvalidProbabilityRejected:
    def test_probability_above_1(self):
        data = _valid_record_dict(probability=1.5)
        is_valid, errors = validate_record(data)
        assert not is_valid
        assert errors

    def test_probability_below_0(self):
        data = _valid_record_dict(probability=-0.1)
        is_valid, errors = validate_record(data)
        assert not is_valid

    def test_probability_exactly_0(self):
        data = _valid_record_dict(probability=0.0)
        record = MedicalRecord.model_validate(data)
        assert record.probability == 0.0

    def test_probability_exactly_1(self):
        data = _valid_record_dict(probability=1.0)
        record = MedicalRecord.model_validate(data)
        assert record.probability == 1.0


class TestMissingRequiredField:
    def test_missing_disease_id(self):
        data = _valid_record_dict()
        del data["disease_id"]
        is_valid, errors = validate_record(data)
        assert not is_valid

    def test_missing_symptoms(self):
        data = _valid_record_dict()
        del data["symptoms"]
        is_valid, errors = validate_record(data)
        assert not is_valid

    def test_empty_symptoms_list(self):
        data = _valid_record_dict(symptoms=[])
        is_valid, errors = validate_record(data)
        assert not is_valid

    def test_blank_symptoms_rejected(self):
        data = _valid_record_dict(symptoms=["  ", ""])
        is_valid, errors = validate_record(data)
        assert not is_valid

    def test_invalid_age_group(self):
        data = _valid_record_dict(age_group="toddler")
        is_valid, errors = validate_record(data)
        assert not is_valid

    def test_invalid_gender(self):
        data = _valid_record_dict(gender="unknown_gender")
        is_valid, errors = validate_record(data)
        assert not is_valid


class TestValidateRecordFunction:
    def test_valid_returns_true_empty_errors(self):
        data = _valid_record_dict()
        is_valid, errors = validate_record(data)
        assert is_valid is True
        assert errors == []

    def test_invalid_returns_false_with_errors(self):
        is_valid, errors = validate_record({"garbage": "data"})
        assert is_valid is False
        assert len(errors) > 0

    def test_errors_are_strings(self):
        _, errors = validate_record({"disease_id": "x", "probability": 999})
        for e in errors:
            assert isinstance(e, str)


class TestRecordToDict:
    def test_returns_dict(self):
        record = MedicalRecord.model_validate(_valid_record_dict())
        d = record_to_dict(record)
        assert isinstance(d, dict)

    def test_datetime_serialised_as_string(self):
        record = MedicalRecord.model_validate(_valid_record_dict())
        d = record_to_dict(record)
        assert isinstance(d["created_at"], str)

    def test_drugs_serialised_as_dicts(self):
        data = _valid_record_dict(
            drugs=[{"name": "Aspirin", "dose": "100mg", "route": "oral"}]
        )
        record = MedicalRecord.model_validate(data)
        d = record_to_dict(record)
        assert all(isinstance(drug, dict) for drug in d["drugs"])

    def test_all_required_keys_present(self):
        record = MedicalRecord.model_validate(_valid_record_dict())
        d = record_to_dict(record)
        for key in ("record_id", "disease_id", "disease_name", "symptoms",
                    "age_group", "gender", "probability", "urgency"):
            assert key in d
