"""CLI entry-point for the 1M Medical Dataset Pipeline."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from collections import defaultdict


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_ingest(args: argparse.Namespace) -> None:
    """Run disease + symptom ingestion phases."""
    from pipeline.build_dataset import DatasetBuilder
    from storage.mongo_store import MongoStore

    store = MongoStore()
    builder = DatasetBuilder(store)
    diseases = builder.run_disease_ingestion()
    relations = builder.run_symptom_mapping()
    print(f"✓ Ingested {diseases} diseases and {relations} symptom relations.")


def cmd_enrich(args: argparse.Namespace) -> None:
    """Run treatment enrichment phase."""
    from pipeline.build_dataset import DatasetBuilder
    from storage.mongo_store import MongoStore

    store = MongoStore()
    builder = DatasetBuilder(store)
    count = builder.run_treatment_enrichment()
    print(f"✓ Enriched {count} disease records with treatment data.")


def cmd_build(args: argparse.Namespace) -> None:
    """Run full pipeline to target row count."""
    from pipeline.build_dataset import DatasetBuilder
    from storage.mongo_store import MongoStore

    store = MongoStore()
    builder = DatasetBuilder(store)
    summary = builder.run_all(target=args.target)
    print("\n=== Pipeline Summary ===")
    for key, val in summary.items():
        if key != "stats":
            print(f"  {key:<30} {val}")
    print("\nCollection stats:")
    for key, val in summary.get("stats", {}).items():
        print(f"  {key:<30} {val}")


def cmd_validate(args: argparse.Namespace) -> None:
    """Run data quality gate on stored records."""
    from data_quality.validators import DataQualityGate
    from storage.mongo_store import MongoStore

    store = MongoStore()
    limit = getattr(args, "limit", 10_000) or 10_000
    df = store.export_to_dataframe(limit=limit)
    if df.empty:
        print("No records found in final_rows collection.")
        return

    records = df.to_dict(orient="records")
    gate = DataQualityGate()
    report = gate.run_all_checks(records)
    gate.print_report(report)


def cmd_export(args: argparse.Namespace) -> None:
    """Export final_rows to a Parquet file."""
    from storage.mongo_store import MongoStore

    store = MongoStore()
    output = Path(args.output or "medical_dataset.parquet")
    limit = getattr(args, "limit", None)
    df = store.export_to_dataframe(limit=limit)
    if df.empty:
        print("No records to export.")
        return
    df.to_parquet(output, index=False)
    print(f"✓ Exported {len(df):,} records to {output}")


def cmd_stats(args: argparse.Namespace) -> None:
    """Show MongoDB collection statistics."""
    from storage.mongo_store import MongoStore

    store = MongoStore()
    stats = store.get_stats()
    print("\n=== MongoDB Statistics ===")
    for key, val in stats.items():
        print(f"  {key:<30} {val}")


def cmd_demo(args: argparse.Namespace) -> None:
    """Run a minimal offline demo using only built-in seed data."""
    from config.schema import validate_record
    from config.settings import settings
    from data_quality.validators import DataQualityGate
    from processors.probability_engine import ProbabilityEngine
    from processors.synthetic_generator import SyntheticGenerator
    from processors.urgency_rules import UrgencyEngine
    from sources.symptom_connectors import _DISEASE_SYMPTOMS
    from sources.treatment_connectors import _DRUG_DATA, _TREATMENT_DATA

    print("🏥 Medical Dataset Pipeline – DEMO MODE (offline, no API keys required)")
    print("=" * 65)

    # Build disease-symptom map from seed data
    disease_symptom_map: dict = {}
    for disease_name, symptoms in _DISEASE_SYMPTOMS.items():
        did = "seed-" + disease_name.lower().replace(" ", "-")
        disease_symptom_map[did] = {
            "disease_name": disease_name,
            "symptoms": [{"name": sym, "probability": prob} for sym, prob in symptoms],
        }

    print(f"  Loaded {len(disease_symptom_map)} diseases from built-in seed data")

    # Build probability map
    engine = ProbabilityEngine()
    relations: list = []
    for did, info in disease_symptom_map.items():
        for sym in info["symptoms"]:
            relations.append({
                "disease_id": did,
                "disease_name": info["disease_name"],
                "symptom_name": sym["name"],
                "weight": sym["probability"],
                "source": "symcat",
            })
    probability_map = engine.compute(relations)
    print(f"  Computed probabilities for {len(probability_map)} disease-symptom pairs")

    # Build treatment / drug maps
    treatment_map = dict(_TREATMENT_DATA)
    dmap: dict = defaultdict(list)
    for drug_rec in _DRUG_DATA:
        dname = drug_rec.get("drug_name", "")
        route = drug_rec.get("route", "oral")
        for indication in drug_rec.get("indications", []):
            dmap[indication].append({"name": dname, "dose": None, "route": route})
    drug_map = dict(dmap)

    # Generate demo records
    urgency_engine = UrgencyEngine()
    generator = SyntheticGenerator(
        disease_symptom_map=disease_symptom_map,
        probability_map=probability_map,
        urgency_engine=urgency_engine,
        treatment_map=treatment_map,
        drug_map=drug_map,
    )

    n_records = getattr(args, "count", 1000) or 1000
    disease_ids = list(disease_symptom_map.keys())
    records: list = []
    for i in range(n_records):
        did = disease_ids[i % len(disease_ids)]
        rec = generator.generate_record(did)
        records.append(rec)

    print(f"  Generated {len(records):,} synthetic demo records")

    # Validate
    gate = DataQualityGate()
    report = gate.run_all_checks(records)

    print("\n  Sample records (first 3):")
    for rec in records[:3]:
        print(f"    [{rec['disease_name']}] symptoms={rec['symptoms'][:3]}... "
              f"urgency={rec['urgency']} age={rec['age_group']} gender={rec['gender']}")

    print()
    gate.print_report(report)
    print("✅ Demo complete.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="1M Medical Dataset Pipeline CLI",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Run disease + symptom ingestion phases")
    p_ingest.set_defaults(func=cmd_ingest)

    p_enrich = sub.add_parser("enrich", help="Run treatment enrichment phase")
    p_enrich.set_defaults(func=cmd_enrich)

    p_build = sub.add_parser("build", help="Run full pipeline to target row count")
    p_build.add_argument("--target", type=int, default=1_000_000,
                         help="Target number of rows (default: 1,000,000)")
    p_build.set_defaults(func=cmd_build)

    p_validate = sub.add_parser("validate", help="Run data quality gate on stored records")
    p_validate.add_argument("--limit", type=int, default=10_000)
    p_validate.set_defaults(func=cmd_validate)

    p_export = sub.add_parser("export", help="Export final_rows to Parquet")
    p_export.add_argument("--output", default="medical_dataset.parquet")
    p_export.add_argument("--limit", type=int, default=None)
    p_export.set_defaults(func=cmd_export)

    p_stats = sub.add_parser("stats", help="Show MongoDB collection statistics")
    p_stats.set_defaults(func=cmd_stats)

    p_demo = sub.add_parser("demo", help="Run offline demo (no API keys needed)")
    p_demo.add_argument("--count", type=int, default=1000,
                        help="Number of demo records to generate (default: 1000)")
    p_demo.set_defaults(func=cmd_demo)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.log_level)

    try:
        args.func(args)
    except ConnectionError as exc:
        logging.error("Database connection error: %s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
    except Exception as exc:
        logging.exception("Unexpected error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
