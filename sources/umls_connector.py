"""UMLS (Unified Medical Language System) connector."""
from __future__ import annotations

import logging
from typing import Iterator

import requests

from config.settings import settings
from sources.base import BaseConnector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in fallback – extends core disease list with common conditions
# ---------------------------------------------------------------------------
_UMLS_SEED: list[dict] = [
    {"cui": "C0020538", "name": "Hypertension", "synonyms": ["high blood pressure", "arterial hypertension", "HTN"]},
    {"cui": "C0011849", "name": "Diabetes mellitus", "synonyms": ["DM", "sugar diabetes"]},
    {"cui": "C0027051", "name": "Myocardial infarction", "synonyms": ["heart attack", "MI", "cardiac infarction"]},
    {"cui": "C0038454", "name": "Cerebrovascular accident", "synonyms": ["stroke", "CVA", "brain attack"]},
    {"cui": "C0004096", "name": "Asthma", "synonyms": ["bronchial asthma", "reactive airway disease"]},
    {"cui": "C0024117", "name": "COPD", "synonyms": ["chronic obstructive pulmonary disease", "emphysema"]},
    {"cui": "C0018802", "name": "Heart failure", "synonyms": ["congestive heart failure", "CHF", "cardiac failure"]},
    {"cui": "C0007097", "name": "Carcinoma", "synonyms": ["cancer", "malignant neoplasm", "carcinoma NOS"]},
    {"cui": "C0003469", "name": "Anxiety disorder", "synonyms": ["anxiety", "anxiety neurosis", "panic disorder"]},
    {"cui": "C0011570", "name": "Depression", "synonyms": ["major depressive disorder", "clinical depression"]},
    {"cui": "C0235974", "name": "Pancreatic cancer", "synonyms": ["cancer of pancreas", "pancreatic carcinoma"]},
    {"cui": "C0009319", "name": "Colitis", "synonyms": ["bowel inflammation", "inflammatory colitis"]},
    {"cui": "C0040682", "name": "Trachoma", "synonyms": ["granular conjunctivitis", "Egyptian ophthalmia"]},
    {"cui": "C0009325", "name": "Colon cancer", "synonyms": ["colorectal cancer", "bowel cancer", "CRC"]},
    {"cui": "C0032453", "name": "Polycystic ovary syndrome", "synonyms": ["PCOS", "Stein-Leventhal syndrome"]},
    {"cui": "C0003864", "name": "Rheumatoid arthritis", "synonyms": ["RA", "inflammatory arthritis"]},
    {"cui": "C0029408", "name": "Osteoarthritis", "synonyms": ["OA", "degenerative joint disease"]},
    {"cui": "C0023418", "name": "Leukemia", "synonyms": ["blood cancer", "leukaemia"]},
    {"cui": "C0024299", "name": "Lymphoma", "synonyms": ["Hodgkin lymphoma", "non-Hodgkin lymphoma"]},
    {"cui": "C0006142", "name": "Breast cancer", "synonyms": ["mammary carcinoma", "breast carcinoma"]},
    {"cui": "C0376358", "name": "Prostate cancer", "synonyms": ["prostatic carcinoma", "adenocarcinoma of prostate"]},
    {"cui": "C0042029", "name": "Urinary tract infection", "synonyms": ["UTI", "cystitis", "bladder infection"]},
    {"cui": "C0022650", "name": "Kidney stones", "synonyms": ["nephrolithiasis", "urolithiasis", "renal calculi"]},
    {"cui": "C0017168", "name": "Gastroesophageal reflux disease", "synonyms": ["GERD", "acid reflux"]},
    {"cui": "C0030567", "name": "Parkinson disease", "synonyms": ["Parkinson's", "PD", "paralysis agitans"]},
    {"cui": "C0002395", "name": "Alzheimer disease", "synonyms": ["Alzheimer's", "AD", "senile dementia"]},
    {"cui": "C0014544", "name": "Epilepsy", "synonyms": ["seizure disorder", "convulsive disorder"]},
    {"cui": "C0026769", "name": "Multiple sclerosis", "synonyms": ["MS", "disseminated sclerosis"]},
    {"cui": "C0020676", "name": "Hypothyroidism", "synonyms": ["underactive thyroid", "myxedema"]},
    {"cui": "C0020550", "name": "Hyperthyroidism", "synonyms": ["overactive thyroid", "thyrotoxicosis"]},
    {"cui": "C0019080", "name": "Viral hepatitis", "synonyms": ["hepatitis A", "hepatitis B", "hepatitis C"]},
    {"cui": "C0023890", "name": "Cirrhosis of liver", "synonyms": ["liver cirrhosis", "hepatic cirrhosis"]},
    {"cui": "C0030567", "name": "Peptic ulcer", "synonyms": ["stomach ulcer", "gastric ulcer", "duodenal ulcer"]},
    {"cui": "C0007787", "name": "Transient ischemic attack", "synonyms": ["TIA", "mini stroke"]},
    {"cui": "C0003123", "name": "Anaphylaxis", "synonyms": ["anaphylactic shock", "severe allergic reaction"]},
    {"cui": "C0032326", "name": "Pneumonia", "synonyms": ["lung infection", "pulmonary infection"]},
    {"cui": "C0036690", "name": "Septicemia", "synonyms": ["sepsis", "blood poisoning", "bacteremia"]},
    {"cui": "C0014336", "name": "Endocarditis", "synonyms": ["heart valve infection", "infective endocarditis"]},
    {"cui": "C0013404", "name": "Dyspnea", "synonyms": ["shortness of breath", "breathlessness", "SOB"]},
    {"cui": "C0037277", "name": "Social phobia", "synonyms": ["social anxiety disorder", "social phobia"]},
    {"cui": "C0041327", "name": "Tuberculosis", "synonyms": ["TB", "pulmonary tuberculosis"]},
    {"cui": "C0024115", "name": "Lung disease", "synonyms": ["pulmonary disease", "respiratory disease"]},
    {"cui": "C0038172", "name": "Staphylococcal infection", "synonyms": ["staph infection", "MRSA"]},
    {"cui": "C0022354", "name": "Jaundice", "synonyms": ["icterus", "yellow skin", "hyperbilirubinemia"]},
    {"cui": "C0018021", "name": "Goiter", "synonyms": ["thyroid enlargement", "enlarged thyroid"]},
    {"cui": "C0040053", "name": "Thrombosis", "synonyms": ["blood clot", "thrombus", "clotting disorder"]},
    {"cui": "C0023895", "name": "Liver cancer", "synonyms": ["hepatocellular carcinoma", "HCC", "liver carcinoma"]},
    {"cui": "C0019163", "name": "Hepatitis B", "synonyms": ["HBV infection", "serum hepatitis"]},
    {"cui": "C0019196", "name": "Hepatitis C", "synonyms": ["HCV infection", "hepatitis C virus"]},
    {"cui": "C0042384", "name": "Vasculitis", "synonyms": ["blood vessel inflammation", "vascular inflammation"]},
]


class UMLSConnector(BaseConnector):
    """Connector for UMLS REST API disease/concept retrieval.

    Falls back to built-in seed data when no API key is configured.
    """

    source_name = "umls"

    # Semantic types that represent diseases / disorders
    _DISEASE_STYS = {"T047", "T048", "T049", "T050", "T184", "T019"}

    def fetch(self, **kwargs) -> Iterator[dict]:
        if not settings.UMLS_API_KEY:
            logger.info("UMLS: no API key – using built-in seed (%d concepts)", len(_UMLS_SEED))
            yield from _UMLS_SEED
            return

        session = requests.Session()
        base = settings.UMLS_BASE_URL
        key = settings.UMLS_API_KEY

        # Search for disease-related CUIs
        search_terms = [
            "disease", "disorder", "syndrome", "infection", "cancer",
            "failure", "injury", "deficiency", "inflammation",
        ]
        seen: set[str] = set()
        for term in search_terms:
            try:
                params = {
                    "string": term,
                    "apiKey": key,
                    "searchType": "normalizedWords",
                    "sabs": "SNOMEDCT_US,ICD10CM,MESH",
                    "returnIdType": "concept",
                    "pageSize": 25,
                }
                resp = session.get(f"{base}/search/current", params=params, timeout=20)
                resp.raise_for_status()
                results = resp.json().get("result", {}).get("results", [])
                for r in results:
                    cui = r.get("ui", "")
                    if cui and cui not in seen:
                        seen.add(cui)
                        yield {"cui": cui, "name": r.get("name", ""), "synonyms": []}
            except Exception as exc:
                logger.warning("UMLS search failed for '%s': %s", term, exc)

    def normalize(self, raw: dict) -> dict:
        cui = raw.get("cui", "")
        return {
            "disease_id": f"UMLS:{cui}",
            "disease_name": raw.get("name", ""),
            "synonyms": raw.get("synonyms", []),
            "source": self.source_name,
            "cui": cui,
        }
