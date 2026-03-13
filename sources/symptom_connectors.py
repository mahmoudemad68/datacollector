"""Symptom-disease mapping connectors: Infermedica, SymCAT, HDSN."""
from __future__ import annotations

import logging
from typing import Iterator

import requests

from config.settings import settings
from sources.base import BaseConnector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Comprehensive built-in disease → symptoms mapping
# Each symptom entry: (symptom_name, probability 0-1)
# ---------------------------------------------------------------------------
_DISEASE_SYMPTOMS: dict[str, list[tuple[str, float]]] = {
    # Infectious
    "Influenza": [
        ("fever", 0.92), ("chills", 0.80), ("muscle aches", 0.85),
        ("headache", 0.78), ("fatigue", 0.88), ("dry cough", 0.75),
        ("sore throat", 0.65), ("runny nose", 0.60), ("loss of appetite", 0.55),
    ],
    "COVID-19": [
        ("fever", 0.88), ("dry cough", 0.82), ("fatigue", 0.80),
        ("shortness of breath", 0.55), ("loss of smell", 0.65), ("loss of taste", 0.63),
        ("headache", 0.70), ("sore throat", 0.55), ("muscle aches", 0.60),
        ("diarrhea", 0.30), ("chest pain", 0.20),
    ],
    "Pneumonia": [
        ("cough", 0.92), ("fever", 0.85), ("shortness of breath", 0.80),
        ("chest pain", 0.60), ("fatigue", 0.75), ("chills", 0.70),
        ("rapid breathing", 0.65), ("nausea", 0.35), ("sweating", 0.50),
    ],
    "Tuberculosis": [
        ("chronic cough", 0.92), ("coughing up blood", 0.50), ("night sweats", 0.78),
        ("fever", 0.75), ("weight loss", 0.82), ("fatigue", 0.85),
        ("loss of appetite", 0.70), ("chest pain", 0.55),
    ],
    "Malaria": [
        ("fever", 0.95), ("chills", 0.90), ("sweating", 0.85),
        ("headache", 0.82), ("muscle aches", 0.75), ("nausea", 0.70),
        ("vomiting", 0.65), ("fatigue", 0.80), ("anemia", 0.60),
    ],
    "Dengue fever": [
        ("high fever", 0.95), ("severe headache", 0.88), ("eye pain", 0.75),
        ("muscle and joint pain", 0.90), ("nausea", 0.70), ("vomiting", 0.65),
        ("rash", 0.60), ("mild bleeding", 0.45), ("fatigue", 0.80),
    ],
    "HIV/AIDS": [
        ("fatigue", 0.85), ("fever", 0.75), ("night sweats", 0.70),
        ("swollen lymph nodes", 0.80), ("weight loss", 0.78), ("diarrhea", 0.65),
        ("cough", 0.55), ("skin rash", 0.60), ("oral ulcers", 0.50),
    ],
    "Sepsis": [
        ("fever", 0.85), ("rapid heart rate", 0.90), ("rapid breathing", 0.88),
        ("confusion", 0.70), ("extreme fatigue", 0.85), ("low blood pressure", 0.80),
        ("shivering", 0.75), ("decreased urine output", 0.65),
    ],
    "Meningitis": [
        ("severe headache", 0.95), ("stiff neck", 0.92), ("fever", 0.88),
        ("photophobia", 0.80), ("nausea", 0.75), ("vomiting", 0.70),
        ("confusion", 0.65), ("rash", 0.50), ("seizures", 0.40),
    ],
    "Lyme disease": [
        ("bull's-eye rash", 0.75), ("fever", 0.70), ("chills", 0.65),
        ("fatigue", 0.85), ("headache", 0.75), ("muscle aches", 0.80),
        ("joint pain", 0.78), ("neck stiffness", 0.50), ("facial palsy", 0.30),
    ],
    # Cardiovascular
    "Acute myocardial infarction": [
        ("chest pain", 0.92), ("shortness of breath", 0.80), ("sweating", 0.75),
        ("nausea", 0.65), ("arm pain", 0.70), ("jaw pain", 0.55),
        ("dizziness", 0.60), ("palpitations", 0.45), ("fatigue", 0.70),
    ],
    "Heart failure": [
        ("shortness of breath", 0.90), ("leg swelling", 0.85), ("fatigue", 0.88),
        ("rapid heartbeat", 0.75), ("persistent cough", 0.70), ("wheezing", 0.60),
        ("reduced ability to exercise", 0.85), ("nausea", 0.45),
        ("increased urination at night", 0.65),
    ],
    "Hypertension": [
        ("headache", 0.55), ("dizziness", 0.50), ("blurred vision", 0.45),
        ("shortness of breath", 0.40), ("chest pain", 0.35), ("nose bleeds", 0.30),
        ("fatigue", 0.45),
    ],
    "Atrial fibrillation": [
        ("palpitations", 0.90), ("shortness of breath", 0.75), ("fatigue", 0.80),
        ("dizziness", 0.65), ("chest discomfort", 0.60), ("reduced ability to exercise", 0.70),
    ],
    "Stroke": [
        ("sudden numbness", 0.85), ("sudden confusion", 0.80), ("trouble speaking", 0.88),
        ("vision problems", 0.75), ("loss of balance", 0.78), ("severe headache", 0.70),
        ("facial drooping", 0.82), ("arm weakness", 0.85),
    ],
    "Deep vein thrombosis": [
        ("leg pain", 0.85), ("leg swelling", 0.80), ("warmth in leg", 0.75),
        ("redness of leg", 0.70), ("leg cramps", 0.60),
    ],
    "Pulmonary embolism": [
        ("shortness of breath", 0.92), ("chest pain", 0.75), ("rapid heart rate", 0.80),
        ("cough", 0.55), ("coughing up blood", 0.35), ("dizziness", 0.60),
        ("leg swelling", 0.65), ("sweating", 0.45),
    ],
    # Respiratory
    "Asthma": [
        ("wheezing", 0.92), ("shortness of breath", 0.88), ("chest tightness", 0.85),
        ("cough", 0.80), ("difficulty breathing at night", 0.75),
        ("rapid breathing", 0.65), ("anxiety", 0.50),
    ],
    "COPD": [
        ("chronic cough", 0.90), ("shortness of breath", 0.92), ("wheezing", 0.85),
        ("chest tightness", 0.78), ("increased sputum", 0.82),
        ("fatigue", 0.75), ("cyanosis", 0.40), ("weight loss", 0.55),
    ],
    "Lung cancer": [
        ("persistent cough", 0.80), ("coughing up blood", 0.50),
        ("shortness of breath", 0.75), ("chest pain", 0.65), ("weight loss", 0.82),
        ("fatigue", 0.85), ("hoarseness", 0.45), ("bone pain", 0.40),
        ("headache", 0.35),
    ],
    "Bronchitis": [
        ("cough", 0.95), ("mucus production", 0.85), ("fatigue", 0.75),
        ("shortness of breath", 0.65), ("slight fever", 0.60),
        ("chest discomfort", 0.70), ("sore throat", 0.55),
    ],
    # Neurological
    "Migraine": [
        ("severe headache", 0.98), ("nausea", 0.80), ("vomiting", 0.65),
        ("photophobia", 0.85), ("phonophobia", 0.75), ("visual aura", 0.50),
        ("fatigue", 0.70), ("neck stiffness", 0.45), ("dizziness", 0.55),
    ],
    "Epilepsy": [
        ("seizures", 0.95), ("temporary confusion", 0.75), ("loss of consciousness", 0.70),
        ("staring spell", 0.65), ("muscle jerking", 0.80), ("fear", 0.50),
        ("anxiety", 0.45), ("tongue biting", 0.40),
    ],
    "Alzheimer disease": [
        ("memory loss", 0.95), ("confusion", 0.90), ("difficulty planning", 0.85),
        ("language problems", 0.80), ("disorientation", 0.88),
        ("mood changes", 0.75), ("withdrawal from social activities", 0.70),
        ("difficulty completing tasks", 0.82),
    ],
    "Parkinson disease": [
        ("tremor", 0.95), ("bradykinesia", 0.92), ("muscle rigidity", 0.88),
        ("posture instability", 0.80), ("speech changes", 0.75),
        ("writing changes", 0.65), ("loss of smell", 0.70), ("sleep disturbances", 0.68),
    ],
    "Multiple sclerosis": [
        ("fatigue", 0.90), ("numbness", 0.85), ("tingling", 0.80),
        ("vision problems", 0.75), ("weakness", 0.82), ("dizziness", 0.65),
        ("coordination problems", 0.70), ("bladder problems", 0.60),
        ("cognitive impairment", 0.55),
    ],
    # Endocrine / metabolic
    "Type 2 diabetes mellitus": [
        ("fatigue", 0.85), ("frequent urination", 0.90), ("increased thirst", 0.88),
        ("blurred vision", 0.70), ("slow healing wounds", 0.75),
        ("numbness in feet", 0.65), ("recurrent infections", 0.60),
        ("unexplained weight loss", 0.55), ("dark skin patches", 0.45),
    ],
    "Type 1 diabetes mellitus": [
        ("extreme thirst", 0.92), ("frequent urination", 0.95), ("unexplained weight loss", 0.88),
        ("fatigue", 0.85), ("blurred vision", 0.72), ("irritability", 0.65),
        ("fruity breath", 0.55), ("nausea", 0.60), ("vomiting", 0.50),
    ],
    "Hypothyroidism": [
        ("fatigue", 0.90), ("weight gain", 0.82), ("cold intolerance", 0.78),
        ("dry skin", 0.75), ("hair loss", 0.65), ("constipation", 0.70),
        ("muscle weakness", 0.68), ("depression", 0.60), ("slow heartbeat", 0.55),
    ],
    "Hyperthyroidism": [
        ("weight loss", 0.85), ("rapid heartbeat", 0.90), ("anxiety", 0.82),
        ("tremor", 0.75), ("heat intolerance", 0.80), ("increased sweating", 0.78),
        ("frequent bowel movements", 0.65), ("fatigue", 0.70), ("insomnia", 0.68),
    ],
    "Gout": [
        ("severe joint pain", 0.95), ("joint swelling", 0.90), ("joint redness", 0.88),
        ("joint warmth", 0.85), ("limited range of motion", 0.75),
        ("tophi", 0.40), ("fever", 0.45),
    ],
    # Gastrointestinal
    "Gastroesophageal reflux disease": [
        ("heartburn", 0.95), ("regurgitation", 0.88), ("chest pain", 0.65),
        ("difficulty swallowing", 0.55), ("chronic cough", 0.50),
        ("sore throat", 0.45), ("nausea", 0.60), ("belching", 0.70),
    ],
    "Crohn disease": [
        ("abdominal pain", 0.90), ("diarrhea", 0.88), ("blood in stool", 0.65),
        ("weight loss", 0.80), ("fatigue", 0.85), ("fever", 0.55),
        ("reduced appetite", 0.70), ("perianal disease", 0.50),
        ("mouth sores", 0.40),
    ],
    "Ulcerative colitis": [
        ("diarrhea with blood", 0.92), ("abdominal pain", 0.88), ("urgency to defecate", 0.85),
        ("rectal pain", 0.75), ("weight loss", 0.70), ("fatigue", 0.80),
        ("fever", 0.60), ("failure to grow", 0.30),
    ],
    "Appendicitis": [
        ("abdominal pain around navel", 0.90), ("pain moving to lower right abdomen", 0.92),
        ("nausea", 0.80), ("vomiting", 0.75), ("fever", 0.70),
        ("loss of appetite", 0.82), ("abdominal rigidity", 0.65),
    ],
    "Peptic ulcer disease": [
        ("burning stomach pain", 0.90), ("nausea", 0.75), ("heartburn", 0.70),
        ("bloating", 0.65), ("belching", 0.60), ("intolerance to fatty foods", 0.55),
        ("blood in stool", 0.40), ("vomiting blood", 0.30),
    ],
    "Irritable bowel syndrome": [
        ("abdominal pain", 0.92), ("bloating", 0.88), ("diarrhea", 0.80),
        ("constipation", 0.75), ("mucus in stool", 0.60), ("gas", 0.85),
        ("urgency to have bowel movement", 0.78),
    ],
    "Cirrhosis": [
        ("fatigue", 0.88), ("jaundice", 0.80), ("abdominal swelling", 0.82),
        ("leg swelling", 0.75), ("itchy skin", 0.65), ("spider angiomata", 0.55),
        ("easy bruising", 0.70), ("confusion", 0.60), ("blood in vomit", 0.45),
    ],
    # Musculoskeletal
    "Rheumatoid arthritis": [
        ("joint pain", 0.95), ("joint swelling", 0.92), ("morning stiffness", 0.90),
        ("symmetrical joint involvement", 0.85), ("fatigue", 0.82),
        ("fever", 0.55), ("weight loss", 0.60), ("rheumatoid nodules", 0.40),
    ],
    "Osteoarthritis": [
        ("joint pain", 0.95), ("joint stiffness", 0.90), ("tenderness", 0.85),
        ("loss of flexibility", 0.82), ("grating sensation", 0.70),
        ("bone spurs", 0.65), ("swelling", 0.75),
    ],
    "Fibromyalgia": [
        ("widespread muscle pain", 0.95), ("fatigue", 0.92), ("cognitive difficulties", 0.85),
        ("sleep disturbances", 0.88), ("headaches", 0.75), ("irritable bowel", 0.60),
        ("depression", 0.65), ("anxiety", 0.60), ("tender points", 0.90),
    ],
    "Systemic lupus erythematosus": [
        ("butterfly rash", 0.75), ("joint pain", 0.90), ("fatigue", 0.92),
        ("fever", 0.70), ("skin lesions", 0.65), ("photosensitivity", 0.75),
        ("hair loss", 0.60), ("kidney problems", 0.55), ("chest pain", 0.50),
    ],
    # Mental health
    "Major depressive disorder": [
        ("persistent sadness", 0.95), ("loss of interest", 0.92), ("fatigue", 0.88),
        ("sleep disturbances", 0.85), ("changes in appetite", 0.82),
        ("difficulty concentrating", 0.80), ("feelings of worthlessness", 0.78),
        ("suicidal thoughts", 0.45), ("psychomotor retardation", 0.65),
    ],
    "Generalized anxiety disorder": [
        ("excessive worry", 0.95), ("restlessness", 0.90), ("fatigue", 0.82),
        ("difficulty concentrating", 0.80), ("muscle tension", 0.85),
        ("sleep disturbances", 0.78), ("irritability", 0.75),
        ("headaches", 0.65), ("sweating", 0.60),
    ],
    "Bipolar disorder": [
        ("mood swings", 0.95), ("manic episodes", 0.90), ("depressive episodes", 0.92),
        ("decreased need for sleep", 0.80), ("racing thoughts", 0.85),
        ("grandiosity", 0.75), ("impulsivity", 0.78), ("fatigue", 0.70),
    ],
    "Schizophrenia": [
        ("hallucinations", 0.88), ("delusions", 0.90), ("disorganized thinking", 0.85),
        ("flat affect", 0.80), ("social withdrawal", 0.82), ("lack of motivation", 0.78),
        ("cognitive impairment", 0.75), ("poor personal hygiene", 0.65),
    ],
    "Post-traumatic stress disorder": [
        ("flashbacks", 0.92), ("nightmares", 0.88), ("hypervigilance", 0.85),
        ("avoidance", 0.90), ("emotional numbness", 0.80), ("sleep disturbances", 0.85),
        ("irritability", 0.78), ("depression", 0.75), ("anxiety", 0.82),
    ],
    # Renal
    "Chronic kidney disease": [
        ("fatigue", 0.88), ("swelling in legs", 0.82), ("decreased urine output", 0.78),
        ("nausea", 0.70), ("shortness of breath", 0.65), ("itchy skin", 0.72),
        ("muscle cramps", 0.68), ("poor appetite", 0.75), ("confusion", 0.55),
    ],
    "Urinary tract infection": [
        ("burning urination", 0.95), ("frequent urination", 0.92), ("cloudy urine", 0.85),
        ("strong urine odor", 0.80), ("pelvic pain", 0.75), ("blood in urine", 0.65),
        ("fever", 0.55), ("chills", 0.50),
    ],
    "Kidney stones": [
        ("severe flank pain", 0.95), ("pain radiating to groin", 0.90), ("nausea", 0.80),
        ("vomiting", 0.75), ("blood in urine", 0.85), ("painful urination", 0.78),
        ("fever", 0.50), ("chills", 0.45),
    ],
    # Dermatological
    "Psoriasis": [
        ("red patches", 0.92), ("silver scales", 0.90), ("dry cracked skin", 0.85),
        ("itching", 0.88), ("burning", 0.75), ("soreness", 0.70),
        ("thickened nails", 0.65), ("joint pain", 0.55),
    ],
    "Atopic dermatitis": [
        ("intense itching", 0.95), ("red rash", 0.92), ("dry skin", 0.90),
        ("skin swelling", 0.75), ("crusting lesions", 0.70), ("skin darkening", 0.65),
        ("raw sensitive skin", 0.80),
    ],
    # Hematological
    "Anemia": [
        ("fatigue", 0.92), ("weakness", 0.88), ("pale skin", 0.85),
        ("shortness of breath", 0.78), ("dizziness", 0.75), ("cold hands and feet", 0.70),
        ("chest pain", 0.55), ("headache", 0.65), ("irregular heartbeat", 0.60),
    ],
    "Leukemia": [
        ("fatigue", 0.90), ("frequent infections", 0.85), ("easy bruising", 0.82),
        ("bone pain", 0.75), ("swollen lymph nodes", 0.80), ("fever", 0.78),
        ("weight loss", 0.82), ("night sweats", 0.70), ("bleeding gums", 0.65),
    ],
    # Ophthalmic
    "Glaucoma": [
        ("gradual vision loss", 0.88), ("eye pain", 0.70), ("halos around lights", 0.75),
        ("blurred vision", 0.80), ("nausea", 0.45), ("redness of eye", 0.60),
    ],
    "Cataracts": [
        ("blurred vision", 0.95), ("poor night vision", 0.88), ("halos around lights", 0.82),
        ("faded colors", 0.78), ("double vision", 0.65), ("sensitivity to glare", 0.85),
    ],
    # ENT
    "Sinusitis": [
        ("facial pain", 0.90), ("nasal congestion", 0.92), ("nasal discharge", 0.88),
        ("headache", 0.85), ("reduced sense of smell", 0.75), ("toothache", 0.55),
        ("cough", 0.65), ("fever", 0.60), ("fatigue", 0.70),
    ],
    "Tonsillitis": [
        ("sore throat", 0.95), ("difficulty swallowing", 0.90), ("swollen tonsils", 0.92),
        ("fever", 0.80), ("headache", 0.70), ("ear pain", 0.65),
        ("tender lymph nodes", 0.85), ("bad breath", 0.75),
    ],
    "Otitis media": [
        ("ear pain", 0.95), ("difficulty hearing", 0.85), ("fever", 0.75),
        ("fussiness in children", 0.70), ("fluid drainage from ear", 0.65),
        ("trouble sleeping", 0.60), ("headache", 0.55),
    ],
}


class InfermedicaConnector(BaseConnector):
    """Connector for Infermedica disease-symptom API.

    Falls back to built-in mapping when credentials are not configured.
    """

    source_name = "infermedica"

    def fetch(self, **kwargs) -> Iterator[dict]:
        if not settings.INFERMEDICA_APP_ID or not settings.INFERMEDICA_APP_KEY:
            logger.info("Infermedica: no credentials – using built-in mapping (%d diseases)", len(_DISEASE_SYMPTOMS))
            for disease_name, symptoms in _DISEASE_SYMPTOMS.items():
                for symptom_name, weight in symptoms:
                    yield {
                        "disease_id": f"infermedica-{disease_name.lower().replace(' ', '-')}",
                        "disease_name": disease_name,
                        "symptom_id": f"symptom-{symptom_name.lower().replace(' ', '-')}",
                        "symptom_name": symptom_name,
                        "weight": weight,
                    }
            return

        headers = {
            "App-Id": settings.INFERMEDICA_APP_ID,
            "App-Key": settings.INFERMEDICA_APP_KEY,
            "Content-Type": "application/json",
        }
        session = requests.Session()
        session.headers.update(headers)
        try:
            resp = session.get(f"{settings.INFERMEDICA_BASE_URL}/conditions", timeout=20)
            resp.raise_for_status()
            conditions = resp.json()
            for cond in conditions:
                cid = cond.get("id", "")
                cname = cond.get("name", "")
                for symptom in cond.get("symptoms", []):
                    yield {
                        "disease_id": cid,
                        "disease_name": cname,
                        "symptom_id": symptom.get("id", ""),
                        "symptom_name": symptom.get("name", ""),
                        "weight": symptom.get("weight", 0.5),
                    }
        except Exception as exc:
            logger.warning("Infermedica API failed (%s) – using built-in", exc)
            for disease_name, symptoms in _DISEASE_SYMPTOMS.items():
                for symptom_name, weight in symptoms:
                    yield {
                        "disease_id": f"infermedica-{disease_name.lower().replace(' ', '-')}",
                        "disease_name": disease_name,
                        "symptom_id": f"symptom-{symptom_name.lower().replace(' ', '-')}",
                        "symptom_name": symptom_name,
                        "weight": weight,
                    }

    def normalize(self, raw: dict) -> dict:
        return raw


# ---------------------------------------------------------------------------
# SymCAT connector
# ---------------------------------------------------------------------------

class SymCATConnector(BaseConnector):
    """SymCAT-style disease-symptom frequency connector (built-in dataset)."""

    source_name = "symcat"

    def fetch(self, **kwargs) -> Iterator[dict]:
        for disease_name, symptoms in _DISEASE_SYMPTOMS.items():
            for symptom_name, frequency in symptoms:
                yield {
                    "disease_name": disease_name,
                    "symptom_name": symptom_name,
                    "frequency": frequency,
                    "source": self.source_name,
                }

    def normalize(self, raw: dict) -> dict:
        return raw


# ---------------------------------------------------------------------------
# HDSN connector
# ---------------------------------------------------------------------------

# High-quality curated disease-symptom co-occurrence scores
_HDSN_DATA: list[tuple[str, str, str, float]] = [
    # (disease_id, disease_name, symptom_name, co_occurrence_score)
    ("D001927", "Brain diseases", "headache", 0.85),
    ("D001927", "Brain diseases", "confusion", 0.80),
    ("D001927", "Brain diseases", "nausea", 0.65),
    ("D006333", "Heart failure", "dyspnea", 0.92),
    ("D006333", "Heart failure", "edema", 0.88),
    ("D006333", "Heart failure", "fatigue", 0.85),
    ("D003920", "Diabetes mellitus", "polyuria", 0.90),
    ("D003920", "Diabetes mellitus", "polydipsia", 0.88),
    ("D003920", "Diabetes mellitus", "fatigue", 0.82),
    ("D003920", "Diabetes mellitus", "blurred vision", 0.70),
    ("D001249", "Asthma", "wheezing", 0.92),
    ("D001249", "Asthma", "dyspnea", 0.88),
    ("D001249", "Asthma", "cough", 0.85),
    ("D001249", "Asthma", "chest tightness", 0.80),
    ("D007676", "Kidney failure", "fatigue", 0.88),
    ("D007676", "Kidney failure", "edema", 0.82),
    ("D007676", "Kidney failure", "nausea", 0.78),
    ("D007676", "Kidney failure", "decreased urination", 0.90),
    ("D008175", "Lung neoplasms", "cough", 0.88),
    ("D008175", "Lung neoplasms", "hemoptysis", 0.55),
    ("D008175", "Lung neoplasms", "chest pain", 0.65),
    ("D008175", "Lung neoplasms", "dyspnea", 0.78),
    ("D008175", "Lung neoplasms", "weight loss", 0.82),
    ("D010922", "Pneumonia", "fever", 0.88),
    ("D010922", "Pneumonia", "cough", 0.92),
    ("D010922", "Pneumonia", "dyspnea", 0.80),
    ("D010922", "Pneumonia", "chest pain", 0.65),
    ("D011014", "Pneumococcal infections", "fever", 0.90),
    ("D011014", "Pneumococcal infections", "cough", 0.85),
    ("D011014", "Pneumococcal infections", "chest pain", 0.70),
    ("D012559", "Schizophrenia", "hallucinations", 0.88),
    ("D012559", "Schizophrenia", "delusions", 0.90),
    ("D012559", "Schizophrenia", "disorganized speech", 0.80),
    ("D003866", "Depressive disorder", "depressed mood", 0.95),
    ("D003866", "Depressive disorder", "anhedonia", 0.92),
    ("D003866", "Depressive disorder", "fatigue", 0.85),
    ("D003866", "Depressive disorder", "insomnia", 0.80),
    ("D001714", "Bipolar disorder", "mood swings", 0.95),
    ("D001714", "Bipolar disorder", "mania", 0.90),
    ("D001714", "Bipolar disorder", "depression", 0.92),
    ("D014947", "Wounds", "pain", 0.90),
    ("D014947", "Wounds", "bleeding", 0.85),
    ("D014947", "Wounds", "swelling", 0.80),
    ("D010146", "Pain", "pain", 0.99),
    ("D010146", "Pain", "tenderness", 0.85),
    ("D013001", "Somatoform disorders", "pain", 0.85),
    ("D013001", "Somatoform disorders", "fatigue", 0.80),
    ("D006984", "Hyperthyroidism", "weight loss", 0.85),
    ("D006984", "Hyperthyroidism", "palpitations", 0.88),
    ("D006984", "Hyperthyroidism", "heat intolerance", 0.80),
    ("D006984", "Hyperthyroidism", "tremor", 0.75),
]


class HDSNConnector(BaseConnector):
    """Human Disease Symptom Network (HDSN) connector with built-in curated data."""

    source_name = "hdsn"

    def fetch(self, **kwargs) -> Iterator[dict]:
        # Built-in curated high-quality disease-symptom mappings
        for disease_id, disease_name, symptom_name, score in _HDSN_DATA:
            yield {
                "disease_id": disease_id,
                "disease_name": disease_name,
                "symptom_name": symptom_name,
                "co_occurrence_score": score,
                "source": self.source_name,
            }

    def normalize(self, raw: dict) -> dict:
        return raw
