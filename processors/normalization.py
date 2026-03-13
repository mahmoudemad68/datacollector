"""Text normalisation utilities for medical data."""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any


def normalize_text(text: str) -> str:
    """Lowercase, strip whitespace, remove special characters, normalise unicode."""
    if not text:
        return ""
    # Normalise unicode (e.g. accents)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    # Collapse internal whitespace
    text = re.sub(r"\s+", " ", text)
    # Remove characters that are not alphanumeric, space, hyphen, or apostrophe
    text = re.sub(r"[^\w\s\-']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_disease_name(name: str) -> str:
    """Normalise a disease name string.

    Handles comma-inversion patterns such as
    ``"Diabetes, Type 2"`` → ``"type 2 diabetes"``
    and ``"Arthritis, Rheumatoid"`` → ``"rheumatoid arthritis"``.
    """
    if not name:
        return ""
    name = name.strip()
    # Handle "Main, Qualifier" → "Qualifier Main"
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and parts[1]:
            name = f"{parts[1]} {parts[0]}"
    return normalize_text(name)


def normalize_symptom_name(name: str) -> str:
    """Normalise a symptom string."""
    if not name:
        return ""
    # Remove leading "has ", "with ", etc.
    name = re.sub(r"^(has|have|with|experiencing?|reports?)\s+", "", name.lower().strip())
    return normalize_text(name)


def deduplicate_by_key(records: list[dict], key: str) -> list[dict]:
    """Return a deduplicated list of dicts keeping the first occurrence per *key* value."""
    seen: set = set()
    result: list[dict] = []
    for rec in records:
        val = rec.get(key)
        if val not in seen:
            seen.add(val)
            result.append(rec)
    return result


def merge_synonyms(records: list[dict]) -> dict[str, dict]:
    """Merge records that share the same ``disease_name`` into one record with
    combined synonyms.

    Returns a mapping ``{normalized_disease_name: merged_record}``.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        key = normalize_disease_name(rec.get("disease_name", rec.get("name", "")))
        groups[key].append(rec)

    merged: dict[str, dict] = {}
    for key, recs in groups.items():
        base = dict(recs[0])
        all_synonyms: list[str] = list(base.get("synonyms", []))
        for r in recs[1:]:
            all_synonyms.extend(r.get("synonyms", []))
            # Prefer the most informative disease_id (non-empty)
            if not base.get("disease_id") and r.get("disease_id"):
                base["disease_id"] = r["disease_id"]
        # Deduplicate synonyms (case-insensitive)
        seen_syns: set[str] = set()
        deduped_syns: list[str] = []
        for s in all_synonyms:
            ns = normalize_text(s)
            if ns and ns not in seen_syns:
                seen_syns.add(ns)
                deduped_syns.append(s)
        base["synonyms"] = deduped_syns
        merged[key] = base
    return merged


def build_symptom_ontology(symptom_lists: list[list[str]]) -> dict[str, str]:
    """Build a mapping from symptom variant/synonym → canonical symptom name.

    The canonical name is chosen as the shortest string among those that
    normalise to the same value.

    Args:
        symptom_lists: Each inner list contains variants of the same symptom.

    Returns:
        ``{variant: canonical_name}``
    """
    ontology: dict[str, str] = {}
    for variants in symptom_lists:
        if not variants:
            continue
        # Pick canonical = shortest non-empty variant
        canonical = min((v.strip() for v in variants if v.strip()), key=len, default="")
        for variant in variants:
            norm = normalize_text(variant)
            if norm:
                ontology[norm] = canonical
    return ontology
