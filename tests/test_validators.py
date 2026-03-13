"""Tests for data_quality/validators.py."""
import uuid
import pytest
from datetime import datetime

from data_quality.validators import DataQualityGate, QualityReport


def _make_record(**overrides) -> dict:
    """Return a valid MedicalRecord-compatible dict."""
    base = {
        "record_id": str(uuid.uuid4()),
        "disease_id": "icd-1A00",
        "disease_name": "Influenza",
        "symptoms": ["fever", "cough", "fatigue"],
        "age_group": "adult",
        "gender": "male",
        "probability": 0.75,
        "urgency": "medium",
        "treatment": ["rest", "hydration"],
        "drugs": [],
        "source_list": ["icd11"],
        "confidence_score": 0.8,
        "is_synthetic": False,
        "created_at": datetime.utcnow().isoformat(),
        "meta": {},
    }
    base.update(overrides)
    return base


class TestValidRecordsPass:
    def test_single_valid_record(self):
        gate = DataQualityGate()
        records = [_make_record()]
        report = gate.run_all_checks(records)
        assert report.valid_count == 1
        assert report.invalid_count == 0

    def test_multiple_valid_records(self):
        gate = DataQualityGate()
        records = [_make_record() for _ in range(50)]
        report = gate.run_all_checks(records)
        assert report.valid_count == 50
        assert report.invalid_count == 0

    def test_empty_records_list(self):
        gate = DataQualityGate()
        report = gate.run_all_checks([])
        assert report.total_checked == 0
        assert report.valid_count == 0


class TestInvalidProbabilityCaught:
    def test_probability_above_1(self):
        gate = DataQualityGate()
        record = _make_record(probability=1.5)
        errors = gate.check_probability_range(record)
        assert errors

    def test_probability_below_0(self):
        gate = DataQualityGate()
        record = _make_record(probability=-0.5)
        errors = gate.check_probability_range(record)
        assert errors

    def test_valid_probability_no_error(self):
        gate = DataQualityGate()
        for prob in [0.0, 0.5, 1.0]:
            errors = gate.check_probability_range(_make_record(probability=prob))
            assert not errors

    def test_missing_probability_is_error(self):
        gate = DataQualityGate()
        record = _make_record()
        del record["probability"]
        errors = gate.check_probability_range(record)
        assert errors

    def test_non_numeric_probability(self):
        gate = DataQualityGate()
        record = _make_record(probability="high")
        errors = gate.check_probability_range(record)
        assert errors


class TestSyntheticRatioExceeded:
    def test_all_synthetic_exceeds_cap(self):
        gate = DataQualityGate()
        records = [_make_record(is_synthetic=True) for _ in range(100)]
        warnings = gate.check_synthetic_ratio(records)
        assert warnings  # 100% > 70% cap

    def test_exactly_at_cap_no_warning(self):
        gate = DataQualityGate()
        n = 100
        synthetic = [_make_record(is_synthetic=True) for _ in range(70)]
        real = [_make_record(is_synthetic=False) for _ in range(30)]
        warnings = gate.check_synthetic_ratio(synthetic + real)
        assert not warnings  # exactly at cap

    def test_below_cap_no_warning(self):
        gate = DataQualityGate()
        synthetic = [_make_record(is_synthetic=True) for _ in range(50)]
        real = [_make_record(is_synthetic=False) for _ in range(50)]
        warnings = gate.check_synthetic_ratio(synthetic + real)
        assert not warnings


class TestClassImbalanceWarning:
    def test_single_disease_dominates(self):
        gate = DataQualityGate()
        # 90 records for one disease, 10 for another → 90% > 20% threshold
        records = [_make_record(disease_name="Influenza") for _ in range(90)]
        records += [_make_record(disease_name="Cholera") for _ in range(10)]
        warnings = gate.check_class_imbalance(records)
        assert any("Influenza" in w for w in warnings)

    def test_balanced_no_warning(self):
        gate = DataQualityGate()
        diseases = [f"Disease_{i}" for i in range(10)]
        records = [_make_record(disease_name=d) for d in diseases for _ in range(5)]
        warnings = gate.check_class_imbalance(records)
        assert not warnings

    def test_empty_list(self):
        gate = DataQualityGate()
        assert gate.check_class_imbalance([]) == []


class TestQualityReportStructure:
    def test_report_is_quality_report_instance(self):
        gate = DataQualityGate()
        report = gate.run_all_checks([_make_record() for _ in range(10)])
        assert isinstance(report, QualityReport)

    def test_total_equals_valid_plus_invalid(self):
        gate = DataQualityGate()
        valid_records = [_make_record() for _ in range(8)]
        invalid_records = [_make_record(probability=99.9) for _ in range(2)]
        report = gate.run_all_checks(valid_records + invalid_records)
        assert report.total_checked == report.valid_count + report.invalid_count

    def test_distributions_populated(self):
        gate = DataQualityGate()
        records = [
            _make_record(disease_name="Flu", age_group="adult", gender="male"),
            _make_record(disease_name="Cold", age_group="child", gender="female"),
        ]
        report = gate.run_all_checks(records)
        assert "adult" in report.age_distribution or "child" in report.age_distribution
        assert "male" in report.gender_distribution or "female" in report.gender_distribution

    def test_synthetic_ratio_computed(self):
        gate = DataQualityGate()
        records = (
            [_make_record(is_synthetic=True) for _ in range(3)]
            + [_make_record(is_synthetic=False) for _ in range(7)]
        )
        report = gate.run_all_checks(records)
        assert report.synthetic_ratio == pytest.approx(0.3)

    def test_print_report_does_not_raise(self, capsys):
        gate = DataQualityGate()
        records = [_make_record() for _ in range(5)]
        report = gate.run_all_checks(records)
        gate.print_report(report)  # should not raise
        captured = capsys.readouterr()
        assert "DATA QUALITY REPORT" in captured.out
