"""Data quality validators and reporting."""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from config.schema import validate_record
from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class QualityReport:
    """Summary of a data quality gate run."""

    total_checked: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    error_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    synthetic_ratio: float = 0.0
    disease_distribution: dict[str, int] = field(default_factory=dict)
    age_distribution: dict[str, int] = field(default_factory=dict)
    gender_distribution: dict[str, int] = field(default_factory=dict)


class DataQualityGate:
    """Run a battery of quality checks over a list of medical records.

    Args:
        max_error_rate: Maximum tolerated fraction of invalid records
            (default 1 %).  If exceeded, :meth:`run_all_checks` will add a
            warning to the report.
    """

    def __init__(self, max_error_rate: float = 0.01) -> None:
        self.max_error_rate = max_error_rate

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_schema(self, record: dict) -> list[str]:
        """Validate *record* against the MedicalRecord Pydantic schema."""
        is_valid, errors = validate_record(record)
        return errors

    def check_probability_range(self, record: dict) -> list[str]:
        """Ensure probability is a float in [0, 1]."""
        errors: list[str] = []
        prob = record.get("probability")
        if prob is None:
            errors.append("probability: field is missing")
        else:
            try:
                p = float(prob)
                if not (0.0 <= p <= 1.0):
                    errors.append(f"probability: value {p} out of range [0, 1]")
            except (TypeError, ValueError):
                errors.append(f"probability: non-numeric value '{prob}'")
        return errors

    def check_required_fields(self, record: dict) -> list[str]:
        """Check that required non-null fields are present."""
        required = ["record_id", "disease_id", "disease_name", "symptoms",
                    "age_group", "gender", "urgency"]
        errors: list[str] = []
        for f in required:
            val = record.get(f)
            if val is None or val == "" or val == []:
                errors.append(f"{f}: required field is missing or empty")
        return errors

    def check_uniqueness(self, records: list[dict]) -> list[str]:
        """Detect duplicate record_id values."""
        ids = [r.get("record_id") for r in records if r.get("record_id")]
        counter = Counter(ids)
        duplicates = [rid for rid, cnt in counter.items() if cnt > 1]
        if duplicates:
            return [f"Duplicate record_ids detected ({len(duplicates)} unique IDs appear more than once)"]
        return []

    def check_class_imbalance(self, records: list[dict]) -> list[str]:
        """Warn if any single disease makes up more than 20 % of records."""
        if not records:
            return []
        disease_counts: Counter = Counter(r.get("disease_name", "unknown") for r in records)
        total = len(records)
        warnings: list[str] = []
        for disease, cnt in disease_counts.items():
            ratio = cnt / total
            if ratio > 0.20:
                warnings.append(
                    f"Class imbalance: '{disease}' represents {ratio:.1%} of records "
                    f"({cnt}/{total})"
                )
        return warnings

    def check_synthetic_ratio(self, records: list[dict]) -> list[str]:
        """Ensure synthetic records do not exceed the configured cap."""
        if not records:
            return []
        synthetic_count = sum(1 for r in records if r.get("is_synthetic"))
        ratio = synthetic_count / len(records)
        if ratio > settings.SYNTHETIC_CAP:
            return [
                f"Synthetic ratio {ratio:.1%} exceeds cap of "
                f"{settings.SYNTHETIC_CAP:.1%} "
                f"({synthetic_count}/{len(records)} records)"
            ]
        return []

    def check_leakage(self, records: list[dict]) -> list[str]:
        """Detect obvious data-leakage patterns (e.g. record_id in symptoms)."""
        warnings: list[str] = []
        for i, r in enumerate(records):
            symptoms = r.get("symptoms", [])
            rid = r.get("record_id", "")
            if rid and any(rid in str(s) for s in symptoms):
                warnings.append(f"Record {i}: record_id leaked into symptoms")
            # Detect exact disease_name in symptoms (perfect leakage)
            dname = r.get("disease_name", "").lower()
            if dname and any(dname == str(s).lower() for s in symptoms):
                warnings.append(f"Record {i}: disease_name appears verbatim in symptoms (leakage risk)")
        return warnings

    # ------------------------------------------------------------------
    # Full run
    # ------------------------------------------------------------------

    def run_all_checks(self, records: list[dict]) -> QualityReport:
        """Run all checks and return a :class:`QualityReport`."""
        report = QualityReport(total_checked=len(records))

        # Per-record checks
        error_counts: dict[str, int] = defaultdict(int)
        for record in records:
            per_record_errors: list[str] = []
            per_record_errors.extend(self.check_required_fields(record))
            per_record_errors.extend(self.check_probability_range(record))
            per_record_errors.extend(self.check_schema(record))
            if per_record_errors:
                report.invalid_count += 1
                for err in per_record_errors:
                    key = err.split(":")[0].strip()
                    error_counts[key] += 1
            else:
                report.valid_count += 1

        report.error_counts = dict(error_counts)

        # Collection-level checks
        report.warnings.extend(self.check_uniqueness(records))
        report.warnings.extend(self.check_class_imbalance(records))
        report.warnings.extend(self.check_synthetic_ratio(records))
        report.warnings.extend(self.check_leakage(records))

        # Error rate guard
        if report.total_checked > 0:
            error_rate = report.invalid_count / report.total_checked
            if error_rate > self.max_error_rate:
                report.warnings.append(
                    f"Error rate {error_rate:.2%} exceeds threshold of {self.max_error_rate:.2%}"
                )

        # Distributions
        if records:
            synthetic_count = sum(1 for r in records if r.get("is_synthetic"))
            report.synthetic_ratio = synthetic_count / len(records)
            report.disease_distribution = dict(
                Counter(r.get("disease_name", "unknown") for r in records).most_common(20)
            )
            report.age_distribution = dict(
                Counter(r.get("age_group", "unknown") for r in records)
            )
            report.gender_distribution = dict(
                Counter(r.get("gender", "unknown") for r in records)
            )

        return report

    # ------------------------------------------------------------------
    # Pretty-print
    # ------------------------------------------------------------------

    def print_report(self, report: QualityReport) -> None:
        """Pretty-print a :class:`QualityReport` to stdout."""
        divider = "=" * 60
        print(divider)
        print("  DATA QUALITY REPORT")
        print(divider)
        print(f"  Total records checked : {report.total_checked:,}")
        print(f"  Valid                 : {report.valid_count:,}")
        print(f"  Invalid               : {report.invalid_count:,}")
        if report.total_checked > 0:
            print(f"  Error rate            : {report.invalid_count / report.total_checked:.2%}")
        print(f"  Synthetic ratio       : {report.synthetic_ratio:.2%}")
        print()

        if report.error_counts:
            print("  Error breakdown:")
            for err_type, cnt in sorted(report.error_counts.items(), key=lambda x: -x[1]):
                print(f"    {err_type:<40} {cnt:>6}")
            print()

        if report.warnings:
            print("  Warnings:")
            for w in report.warnings:
                print(f"    ⚠  {w}")
            print()

        if report.disease_distribution:
            print("  Top diseases (up to 10):")
            for disease, cnt in list(report.disease_distribution.items())[:10]:
                print(f"    {disease:<45} {cnt:>6}")
            print()

        if report.age_distribution:
            print("  Age distribution:")
            for ag, cnt in sorted(report.age_distribution.items()):
                print(f"    {ag:<20} {cnt:>6}")

        if report.gender_distribution:
            print("  Gender distribution:")
            for gd, cnt in sorted(report.gender_distribution.items()):
                print(f"    {gd:<20} {cnt:>6}")

        print(divider)
