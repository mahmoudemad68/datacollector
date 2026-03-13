"""Canonical Pydantic v2 schema for medical records."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AgeGroup(str, Enum):
    INFANT = "infant"
    CHILD = "child"
    ADULT = "adult"
    ELDERLY = "elderly"


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EMERGENCY = "emergency"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class DrugInfo(BaseModel):
    """Minimal drug information record."""

    name: str
    dose: Optional[str] = None
    route: Optional[str] = None


# ---------------------------------------------------------------------------
# Main record
# ---------------------------------------------------------------------------

class MedicalRecord(BaseModel):
    """Canonical representation of a single medical data row."""

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    disease_id: str
    disease_name: str
    symptoms: List[str] = Field(min_length=1)
    age_group: AgeGroup
    gender: Gender
    probability: float = Field(ge=0.0, le=1.0)
    treatment: List[str] = []
    drugs: List[DrugInfo] = []
    urgency: Urgency
    source_list: List[str] = []
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    is_synthetic: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    meta: Dict[str, Any] = {}

    @field_validator("symptoms")
    @classmethod
    def symptoms_not_empty(cls, v: List[str]) -> List[str]:
        """Ensure at least one symptom is present and all are non-blank."""
        cleaned = [s.strip() for s in v if s.strip()]
        if not cleaned:
            raise ValueError("symptoms list must contain at least one non-blank entry")
        return cleaned


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def validate_record(data: dict) -> Tuple[bool, List[str]]:
    """Attempt to build a MedicalRecord from *data*.

    Returns:
        (True, [])          – record is valid.
        (False, [errors])   – record is invalid; errors lists validation messages.
    """
    try:
        MedicalRecord.model_validate(data)
        return True, []
    except Exception as exc:  # pydantic ValidationError
        errors: List[str] = []
        if hasattr(exc, "errors"):
            for err in exc.errors():
                loc = " -> ".join(str(p) for p in err.get("loc", []))
                errors.append(f"{loc}: {err.get('msg', str(err))}")
        else:
            errors.append(str(exc))
        return False, errors


def record_to_dict(record: MedicalRecord) -> dict:
    """Serialise a MedicalRecord to a plain dict (datetime → ISO string)."""
    d = record.model_dump()
    if isinstance(d.get("created_at"), datetime):
        d["created_at"] = d["created_at"].isoformat()
    # Flatten DrugInfo objects
    d["drugs"] = [
        drug if isinstance(drug, dict) else drug.model_dump()
        for drug in record.drugs
    ]
    return d
