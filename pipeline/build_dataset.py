"""Main pipeline orchestrator."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from tqdm import tqdm

from config.settings import settings
from processors.normalization import normalize_disease_name, normalize_symptom_name
from processors.probability_engine import ProbabilityEngine
from processors.synthetic_generator import SyntheticGenerator
from processors.urgency_rules import UrgencyEngine
from sources.icd_connector import ICDConnector
from sources.symptom_connectors import HDSNConnector, InfermedicaConnector, SymCATConnector
from sources.treatment_connectors import (
    ClinicalTrialsConnector,
    MedlinePlusConnector,
    OpenFDAConnector,
)
from sources.umls_connector import UMLSConnector
from storage.mongo_store import MongoStore

logger = logging.getLogger(__name__)


class DatasetBuilder:
    """Orchestrates all phases of the medical dataset pipeline.

    Phases
    ------
    1. Disease ingestion  (ICD-11 + UMLS)
    2. Symptom mapping    (Infermedica + SymCAT + HDSN)
    3. Treatment enrichment (MedlinePlus + openFDA + ClinicalTrials)
    4. Probability & urgency computation
    5. Synthetic generation to reach target row count
    """

    def __init__(self, store: MongoStore) -> None:
        self.store = store
        self._probability_engine = ProbabilityEngine()
        self._urgency_engine = UrgencyEngine()

    # ------------------------------------------------------------------
    # Phase 1 – Disease ingestion
    # ------------------------------------------------------------------

    def run_disease_ingestion(self) -> int:
        """Run ICD-11 and UMLS connectors and store the results."""
        count = 0
        for connector in (ICDConnector(), UMLSConnector()):
            logger.info("Running disease ingestion: %s", connector.source_name)
            for record in connector.run():
                if not record.get("disease_name"):
                    continue
                if not record.get("disease_id"):
                    record["disease_id"] = (
                        f"{connector.source_name}-"
                        + normalize_disease_name(record["disease_name"]).replace(" ", "-")
                    )
                self.store.upsert_disease(record)
                count += 1
        logger.info("Disease ingestion complete: %d diseases stored", count)
        return count

    # ------------------------------------------------------------------
    # Phase 2 – Symptom mapping
    # ------------------------------------------------------------------

    def run_symptom_mapping(self) -> int:
        """Run symptom connectors and store symptoms + relations."""
        all_relations: list[dict] = []

        for connector in (InfermedicaConnector(), SymCATConnector(), HDSNConnector()):
            logger.info("Running symptom mapping: %s", connector.source_name)
            for record in connector.run():
                symptom_name = normalize_symptom_name(record.get("symptom_name", ""))
                if not symptom_name:
                    continue

                # Upsert symptom
                self.store.upsert_symptom({"symptom_name": symptom_name})

                # Build relation
                disease_id = record.get("disease_id") or (
                    f"seed-{normalize_disease_name(record.get('disease_name', '')).replace(' ', '-')}"
                )
                disease_name = record.get("disease_name", "")

                rel = {
                    "disease_id": disease_id,
                    "disease_name": disease_name,
                    "symptom_name": symptom_name,
                    "weight": float(record.get("weight", record.get("frequency", record.get("co_occurrence_score", 0.5)))),
                    "source": record.get("source", connector.source_name),
                }
                all_relations.append(rel)

        # Enrich with computed probabilities
        enriched = self._probability_engine.enrich_relations(all_relations)
        count = 0
        for rel in enriched:
            self.store.upsert_relation(rel)
            count += 1

        logger.info("Symptom mapping complete: %d relations stored", count)
        return count

    # ------------------------------------------------------------------
    # Phase 3 – Treatment enrichment
    # ------------------------------------------------------------------

    def run_treatment_enrichment(self) -> int:
        """Enrich disease documents with treatment info from multiple sources."""
        enriched_count = 0

        # MedlinePlus treatments
        for record in MedlinePlusConnector().run():
            dn = record.get("disease_name", "")
            treatments = record.get("treatments", [])
            if dn and treatments:
                norm = normalize_disease_name(dn)
                # Find disease in store and update
                self.store._db.diseases.update_many(
                    {"$or": [
                        {"disease_name": dn},
                        {"disease_name": {"$regex": f"^{dn}$", "$options": "i"}},
                    ]},
                    {"$addToSet": {"treatments": {"$each": treatments}}},
                )
                enriched_count += 1

        # openFDA drug data
        drug_by_disease: dict[str, list[dict]] = defaultdict(list)
        for record in OpenFDAConnector().run():
            drug_name = record.get("drug_name", "")
            route = record.get("route", "oral")
            for indication in record.get("indications", []):
                norm = normalize_disease_name(str(indication))
                drug_by_disease[indication].append({
                    "name": drug_name,
                    "route": route,
                    "dose": None,
                })

        for disease_name, drugs in drug_by_disease.items():
            if drugs:
                self.store._db.diseases.update_many(
                    {"disease_name": {"$regex": disease_name, "$options": "i"}},
                    {"$addToSet": {"drugs": {"$each": drugs}}},
                )

        # ClinicalTrials interventions
        for record in ClinicalTrialsConnector().run():
            dn = record.get("disease_name", "")
            interventions = record.get("interventions", [])
            if dn and interventions:
                self.store._db.diseases.update_many(
                    {"disease_name": {"$regex": f"^{dn}$", "$options": "i"}},
                    {"$addToSet": {"interventions": {"$each": interventions}}},
                )

        logger.info("Treatment enrichment complete: %d diseases enriched", enriched_count)
        return enriched_count

    # ------------------------------------------------------------------
    # Phase 4 – Probability & urgency
    # ------------------------------------------------------------------

    def run_probability_urgency(self) -> int:
        """Compute and store probability + urgency for all relations."""
        diseases = self.store.get_all_diseases()
        updated = 0
        for disease in diseases:
            did = disease.get("disease_id", "")
            dname = disease.get("disease_name", "")
            relations = self.store.get_relations_for_disease(did)
            symptoms = [r["symptom_name"] for r in relations]
            urgency = self._urgency_engine.classify(dname, symptoms)
            self.store._db.diseases.update_one(
                {"disease_id": did},
                {"$set": {"urgency": urgency.value}},
            )
            updated += 1
        logger.info("Probability/urgency computation complete for %d diseases", updated)
        return updated

    # ------------------------------------------------------------------
    # Phase 5 – Synthetic generation
    # ------------------------------------------------------------------

    def run_synthetic_generation(self, target: int = 1_000_000) -> int:
        """Generate synthetic records until the dataset reaches *target* rows."""
        disease_symptom_map = self.build_disease_symptom_map()
        treatment_map = self.build_treatment_map()
        drug_map = self.build_drug_map()

        # Build probability map from stored relations
        all_relations = list(self.store._db.relations.find({}, {"_id": 0}))
        probability_map = self._probability_engine.compute(all_relations)

        generator = SyntheticGenerator(
            disease_symptom_map=disease_symptom_map,
            probability_map=probability_map,
            urgency_engine=self._urgency_engine,
            treatment_map=treatment_map,
            drug_map=drug_map,
        )

        disease_ids = [
            did for did in disease_symptom_map
            if disease_symptom_map[did].get("symptoms")
        ]

        if not disease_ids:
            logger.warning("No disease-symptom mappings found – cannot generate synthetic records")
            return 0

        current_count = self.store.count("final_rows")
        total_generated = 0
        batch_size = settings.BATCH_SIZE

        with tqdm(total=target, initial=current_count, desc="Generating records", unit="rec") as pbar:
            while current_count < target:
                remaining = target - current_count
                batch_count = min(batch_size, remaining)
                records = generator.generate_batch(
                    disease_ids=disease_ids,
                    count=batch_count,
                    existing_count=current_count,
                    target_total=target,
                )
                if not records:
                    logger.info("Synthetic cap reached at %d records", current_count)
                    break

                inserted = self.store.insert_batch(records)
                total_generated += inserted
                current_count += inserted
                pbar.update(inserted)

                if inserted == 0:
                    break

        logger.info("Synthetic generation complete: %d new records", total_generated)
        return total_generated

    # ------------------------------------------------------------------
    # run_all
    # ------------------------------------------------------------------

    def run_all(self, target: int = 1_000_000) -> dict[str, Any]:
        """Run all pipeline phases in order.

        Returns a summary dict with counts from each phase.
        """
        logger.info("=== Starting full pipeline (target=%d rows) ===", target)
        summary: dict[str, Any] = {}

        summary["diseases_ingested"] = self.run_disease_ingestion()
        summary["relations_mapped"] = self.run_symptom_mapping()
        summary["treatments_enriched"] = self.run_treatment_enrichment()
        summary["urgency_updated"] = self.run_probability_urgency()
        summary["synthetic_generated"] = self.run_synthetic_generation(target=target)
        summary["total_rows"] = self.store.count("final_rows")
        summary["stats"] = self.store.get_stats()

        logger.info("=== Pipeline complete. Summary: %s ===", summary)
        return summary

    # ------------------------------------------------------------------
    # Map builders
    # ------------------------------------------------------------------

    def build_disease_symptom_map(self) -> dict[str, dict]:
        """Build an in-memory disease → symptoms map from stored relations.

        Returns:
            ``{disease_id: {"disease_name": str, "symptoms": [{"name": str, "probability": float}]}}``
        """
        diseases = self.store.get_all_diseases()
        result: dict[str, dict] = {}

        for disease in diseases:
            did = disease.get("disease_id", "")
            dname = disease.get("disease_name", "")
            relations = self.store.get_relations_for_disease(did)
            symptoms = [
                {
                    "name": r["symptom_name"],
                    "probability": float(r.get("probability", r.get("weight", 0.5))),
                }
                for r in relations
                if r.get("symptom_name")
            ]
            if symptoms:
                result[did] = {"disease_name": dname, "symptoms": symptoms}

        # Fallback: use in-memory seed data if DB has no relations
        if not result:
            from sources.symptom_connectors import _DISEASE_SYMPTOMS
            for dname, sym_list in _DISEASE_SYMPTOMS.items():
                did = f"seed-{normalize_disease_name(dname).replace(' ', '-')}"
                result[did] = {
                    "disease_name": dname,
                    "symptoms": [{"name": sym, "probability": prob} for sym, prob in sym_list],
                }

        return result

    def build_treatment_map(self) -> dict[str, list[str]]:
        """Build ``{disease_name: [treatments]}`` from stored diseases."""
        diseases = self.store.get_all_diseases()
        result: dict[str, list[str]] = {}
        for d in diseases:
            treatments = d.get("treatments", [])
            if treatments:
                result[d.get("disease_name", "")] = treatments

        # Fallback to built-in data
        if not result:
            from sources.treatment_connectors import _TREATMENT_DATA
            result = dict(_TREATMENT_DATA)

        return result

    def build_drug_map(self) -> dict[str, list[dict]]:
        """Build ``{disease_name: [drug_dicts]}`` from stored diseases + openFDA."""
        from sources.treatment_connectors import _DRUG_DATA
        result: dict[str, list[dict]] = defaultdict(list)

        for drug_rec in _DRUG_DATA:
            drug_name = drug_rec.get("drug_name", "")
            route = drug_rec.get("route", "oral")
            for indication in drug_rec.get("indications", []):
                result[indication].append({"name": drug_name, "dose": None, "route": route})

        # Also check disease documents
        diseases = self.store.get_all_diseases()
        for d in diseases:
            dname = d.get("disease_name", "")
            for drug in d.get("drugs", []):
                if isinstance(drug, dict) and drug.get("name"):
                    result[dname].append(drug)

        return dict(result)
