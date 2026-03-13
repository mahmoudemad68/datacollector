"""MongoDB storage layer for the medical dataset pipeline."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from config.settings import settings

logger = logging.getLogger(__name__)

try:
    from pymongo import MongoClient, ASCENDING, UpdateOne, errors as mongo_errors
    _PYMONGO_AVAILABLE = True
except ImportError:
    _PYMONGO_AVAILABLE = False
    logger.warning("pymongo not installed – MongoStore will raise on connect")


class MongoStore:
    """Thin MongoDB wrapper that exposes pipeline-centric operations.

    Collections
    -----------
    - ``diseases``    – one document per disease (upserted by disease_id)
    - ``symptoms``    – one document per unique symptom name
    - ``relations``   – disease-symptom relation with probability
    - ``final_rows``  – fully assembled :class:`~config.schema.MedicalRecord` dicts
    """

    def __init__(
        self,
        uri: str | None = None,
        db_name: str | None = None,
    ) -> None:
        if not _PYMONGO_AVAILABLE:
            raise RuntimeError("pymongo is not installed. Run: pip install pymongo")

        self._uri = uri or settings.MONGO_URI
        self._db_name = db_name or settings.MONGO_DB
        try:
            self._client: MongoClient = MongoClient(
                self._uri,
                serverSelectionTimeoutMS=5_000,
                connectTimeoutMS=5_000,
            )
            # Ping to validate connectivity
            self._client.admin.command("ping")
            logger.info("Connected to MongoDB at %s (db=%s)", self._uri, self._db_name)
        except Exception as exc:
            raise ConnectionError(
                f"Cannot connect to MongoDB at {self._uri}. "
                "Ensure MongoDB is running or set MONGO_URI in .env.\n"
                f"Original error: {exc}"
            ) from exc

        self._db = self._client[self._db_name]
        self.create_indexes()

    # ------------------------------------------------------------------
    # Index creation
    # ------------------------------------------------------------------

    def create_indexes(self) -> None:
        """Create indexes on all collections for efficient lookup."""
        try:
            self._db.diseases.create_index([("disease_id", ASCENDING)], unique=True)
            self._db.symptoms.create_index([("symptom_name", ASCENDING)], unique=True)
            self._db.relations.create_index(
                [("disease_id", ASCENDING), ("symptom_name", ASCENDING)],
                unique=True,
            )
            self._db.final_rows.create_index([("record_id", ASCENDING)], unique=True)
            self._db.final_rows.create_index([("disease_id", ASCENDING)])
            self._db.final_rows.create_index([("is_synthetic", ASCENDING)])
        except Exception as exc:
            logger.warning("Index creation issue: %s", exc)

    # ------------------------------------------------------------------
    # Disease operations
    # ------------------------------------------------------------------

    def upsert_disease(self, doc: dict) -> None:
        """Insert or update a disease document by ``disease_id``."""
        did = doc.get("disease_id")
        if not did:
            logger.warning("upsert_disease: missing disease_id – skipping")
            return
        self._db.diseases.update_one(
            {"disease_id": did},
            {"$set": doc},
            upsert=True,
        )

    def get_all_diseases(self) -> list[dict]:
        """Return all disease documents."""
        return list(self._db.diseases.find({}, {"_id": 0}))

    # ------------------------------------------------------------------
    # Symptom operations
    # ------------------------------------------------------------------

    def upsert_symptom(self, doc: dict) -> None:
        """Insert or update a symptom document by normalised ``symptom_name``."""
        name = doc.get("symptom_name", "")
        if not name:
            return
        self._db.symptoms.update_one(
            {"symptom_name": name},
            {"$set": doc},
            upsert=True,
        )

    # ------------------------------------------------------------------
    # Relation operations
    # ------------------------------------------------------------------

    def upsert_relation(self, doc: dict) -> None:
        """Insert or update a disease-symptom relation."""
        did = doc.get("disease_id")
        sym = doc.get("symptom_name")
        if not did or not sym:
            return
        self._db.relations.update_one(
            {"disease_id": did, "symptom_name": sym},
            {"$set": doc},
            upsert=True,
        )

    def get_relations_for_disease(self, disease_id: str) -> list[dict]:
        """Return all symptom relations for a given disease."""
        return list(self._db.relations.find({"disease_id": disease_id}, {"_id": 0}))

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def insert_batch(
        self,
        records: list[dict],
        collection: str = "final_rows",
    ) -> int:
        """Bulk-insert records, silently ignoring duplicates (by record_id).

        Returns:
            Number of records actually inserted.
        """
        if not records:
            return 0
        coll = self._db[collection]
        ops = [
            UpdateOne(
                {"record_id": r["record_id"]},
                {"$setOnInsert": r},
                upsert=True,
            )
            for r in records
            if r.get("record_id")
        ]
        if not ops:
            return 0
        try:
            result = coll.bulk_write(ops, ordered=False)
            inserted = result.upserted_count
            return inserted
        except Exception as exc:
            logger.warning("insert_batch error: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Stats and export
    # ------------------------------------------------------------------

    def count(self, collection: str) -> int:
        """Return approximate document count for *collection*."""
        return self._db[collection].estimated_document_count()

    def get_stats(self) -> dict[str, Any]:
        """Return counts per collection and synthetic ratio of final_rows."""
        total = self.count("final_rows")
        synthetic_count = self._db.final_rows.count_documents({"is_synthetic": True})
        return {
            "diseases": self.count("diseases"),
            "symptoms": self.count("symptoms"),
            "relations": self.count("relations"),
            "final_rows": total,
            "synthetic_count": synthetic_count,
            "real_count": total - synthetic_count,
            "synthetic_ratio": round(synthetic_count / max(total, 1), 4),
        }

    def export_to_dataframe(
        self,
        collection: str = "final_rows",
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Export a collection to a pandas DataFrame.

        Args:
            collection: Collection name (default ``final_rows``).
            limit: Maximum number of rows to return (``None`` = all).
        """
        coll = self._db[collection]
        cursor = coll.find({}, {"_id": 0})
        if limit:
            cursor = cursor.limit(limit)
        docs = list(cursor)
        if not docs:
            return pd.DataFrame()
        df = pd.DataFrame(docs)
        return df
