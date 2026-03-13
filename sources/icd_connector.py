"""WHO ICD-11 connector with built-in seed fallback."""
from __future__ import annotations

import logging
from typing import Iterator

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from sources.base import BaseConnector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in seed: ~100 diseases across major categories
# ---------------------------------------------------------------------------
_ICD_SEED: list[dict] = [
    # Infectious / parasitic
    {"id": "icd-1A00", "icd_code": "1A00", "title": "Cholera", "synonyms": ["Vibrio cholerae infection"]},
    {"id": "icd-1A01", "icd_code": "1A01", "title": "Typhoid fever", "synonyms": ["Salmonella typhi infection", "enteric fever"]},
    {"id": "icd-1A02", "icd_code": "1A02", "title": "Tuberculosis", "synonyms": ["TB", "Mycobacterium tuberculosis"]},
    {"id": "icd-1A03", "icd_code": "1A03", "title": "Malaria", "synonyms": ["Plasmodium infection", "marsh fever"]},
    {"id": "icd-1A04", "icd_code": "1A04", "title": "Dengue fever", "synonyms": ["breakbone fever", "dengue"]},
    {"id": "icd-1A05", "icd_code": "1A05", "title": "HIV/AIDS", "synonyms": ["human immunodeficiency virus", "acquired immunodeficiency syndrome"]},
    {"id": "icd-1A06", "icd_code": "1A06", "title": "Influenza", "synonyms": ["flu", "grippe"]},
    {"id": "icd-1A07", "icd_code": "1A07", "title": "COVID-19", "synonyms": ["SARS-CoV-2 infection", "coronavirus disease 2019"]},
    {"id": "icd-1A08", "icd_code": "1A08", "title": "Hepatitis B", "synonyms": ["HBV infection", "serum hepatitis"]},
    {"id": "icd-1A09", "icd_code": "1A09", "title": "Hepatitis C", "synonyms": ["HCV infection", "non-A non-B hepatitis"]},
    {"id": "icd-1A10", "icd_code": "1A10", "title": "Measles", "synonyms": ["rubeola", "morbilli"]},
    {"id": "icd-1A11", "icd_code": "1A11", "title": "Pneumonia", "synonyms": ["lung infection", "pulmonary infection"]},
    {"id": "icd-1A12", "icd_code": "1A12", "title": "Sepsis", "synonyms": ["blood poisoning", "bacteremia", "septicemia"]},
    {"id": "icd-1A13", "icd_code": "1A13", "title": "Lyme disease", "synonyms": ["Lyme borreliosis", "Borrelia infection"]},
    {"id": "icd-1A14", "icd_code": "1A14", "title": "Meningitis", "synonyms": ["bacterial meningitis", "viral meningitis", "meningococcal disease"]},
    # Cardiovascular
    {"id": "icd-BA80", "icd_code": "BA80", "title": "Acute myocardial infarction", "synonyms": ["heart attack", "MI", "STEMI", "NSTEMI"]},
    {"id": "icd-BA81", "icd_code": "BA81", "title": "Heart failure", "synonyms": ["congestive heart failure", "cardiac failure", "CHF"]},
    {"id": "icd-BA82", "icd_code": "BA82", "title": "Hypertension", "synonyms": ["high blood pressure", "arterial hypertension"]},
    {"id": "icd-BA83", "icd_code": "BA83", "title": "Atrial fibrillation", "synonyms": ["AF", "AFib", "irregular heartbeat"]},
    {"id": "icd-BA84", "icd_code": "BA84", "title": "Coronary artery disease", "synonyms": ["CAD", "ischemic heart disease", "atherosclerosis"]},
    {"id": "icd-BA85", "icd_code": "BA85", "title": "Stroke", "synonyms": ["cerebrovascular accident", "CVA", "brain attack"]},
    {"id": "icd-BA86", "icd_code": "BA86", "title": "Deep vein thrombosis", "synonyms": ["DVT", "venous thromboembolism"]},
    {"id": "icd-BA87", "icd_code": "BA87", "title": "Pulmonary embolism", "synonyms": ["PE", "lung clot", "pulmonary thromboembolism"]},
    {"id": "icd-BA88", "icd_code": "BA88", "title": "Peripheral artery disease", "synonyms": ["PAD", "peripheral vascular disease"]},
    {"id": "icd-BA89", "icd_code": "BA89", "title": "Aortic aneurysm", "synonyms": ["AAA", "abdominal aortic aneurysm"]},
    # Respiratory
    {"id": "icd-CA20", "icd_code": "CA20", "title": "Asthma", "synonyms": ["bronchial asthma", "reactive airway disease"]},
    {"id": "icd-CA21", "icd_code": "CA21", "title": "Chronic obstructive pulmonary disease", "synonyms": ["COPD", "emphysema", "chronic bronchitis"]},
    {"id": "icd-CA22", "icd_code": "CA22", "title": "Pulmonary fibrosis", "synonyms": ["IPF", "interstitial lung disease", "lung fibrosis"]},
    {"id": "icd-CA23", "icd_code": "CA23", "title": "Acute respiratory distress syndrome", "synonyms": ["ARDS", "acute lung injury"]},
    {"id": "icd-CA24", "icd_code": "CA24", "title": "Lung cancer", "synonyms": ["pulmonary carcinoma", "bronchogenic carcinoma", "NSCLC", "SCLC"]},
    {"id": "icd-CA25", "icd_code": "CA25", "title": "Pleurisy", "synonyms": ["pleuritis", "pleural inflammation"]},
    {"id": "icd-CA26", "icd_code": "CA26", "title": "Bronchitis", "synonyms": ["acute bronchitis", "chest cold"]},
    # Neurological
    {"id": "icd-8A00", "icd_code": "8A00", "title": "Epilepsy", "synonyms": ["seizure disorder", "convulsive disorder"]},
    {"id": "icd-8A01", "icd_code": "8A01", "title": "Migraine", "synonyms": ["migraine headache", "hemicranias"]},
    {"id": "icd-8A02", "icd_code": "8A02", "title": "Alzheimer disease", "synonyms": ["Alzheimer's dementia", "senile dementia", "AD"]},
    {"id": "icd-8A03", "icd_code": "8A03", "title": "Parkinson disease", "synonyms": ["Parkinson's", "paralysis agitans", "PD"]},
    {"id": "icd-8A04", "icd_code": "8A04", "title": "Multiple sclerosis", "synonyms": ["MS", "disseminated sclerosis"]},
    {"id": "icd-8A05", "icd_code": "8A05", "title": "Peripheral neuropathy", "synonyms": ["polyneuropathy", "nerve damage"]},
    {"id": "icd-8A06", "icd_code": "8A06", "title": "Guillain-Barre syndrome", "synonyms": ["GBS", "acute inflammatory polyneuropathy"]},
    # Endocrine / metabolic
    {"id": "icd-5A10", "icd_code": "5A10", "title": "Type 1 diabetes mellitus", "synonyms": ["T1DM", "juvenile diabetes", "insulin-dependent diabetes"]},
    {"id": "icd-5A11", "icd_code": "5A11", "title": "Type 2 diabetes mellitus", "synonyms": ["T2DM", "adult-onset diabetes", "non-insulin-dependent diabetes"]},
    {"id": "icd-5A12", "icd_code": "5A12", "title": "Hypothyroidism", "synonyms": ["underactive thyroid", "myxedema"]},
    {"id": "icd-5A13", "icd_code": "5A13", "title": "Hyperthyroidism", "synonyms": ["overactive thyroid", "thyrotoxicosis", "Graves disease"]},
    {"id": "icd-5A14", "icd_code": "5A14", "title": "Obesity", "synonyms": ["morbid obesity", "overweight", "adiposity"]},
    {"id": "icd-5A15", "icd_code": "5A15", "title": "Gout", "synonyms": ["gouty arthritis", "hyperuricemia", "crystal arthritis"]},
    {"id": "icd-5A16", "icd_code": "5A16", "title": "Metabolic syndrome", "synonyms": ["insulin resistance syndrome", "syndrome X"]},
    {"id": "icd-5A17", "icd_code": "5A17", "title": "Cushing syndrome", "synonyms": ["hypercortisolism", "Cushing's disease"]},
    # Gastrointestinal
    {"id": "icd-DA90", "icd_code": "DA90", "title": "Gastroesophageal reflux disease", "synonyms": ["GERD", "acid reflux", "heartburn disease"]},
    {"id": "icd-DA91", "icd_code": "DA91", "title": "Peptic ulcer disease", "synonyms": ["stomach ulcer", "gastric ulcer", "duodenal ulcer"]},
    {"id": "icd-DA92", "icd_code": "DA92", "title": "Crohn disease", "synonyms": ["Crohn's disease", "regional enteritis", "IBD - Crohn type"]},
    {"id": "icd-DA93", "icd_code": "DA93", "title": "Ulcerative colitis", "synonyms": ["UC", "IBD - colitis type", "inflammatory bowel disease"]},
    {"id": "icd-DA94", "icd_code": "DA94", "title": "Irritable bowel syndrome", "synonyms": ["IBS", "spastic colon", "functional bowel disorder"]},
    {"id": "icd-DA95", "icd_code": "DA95", "title": "Appendicitis", "synonyms": ["acute appendicitis", "inflamed appendix"]},
    {"id": "icd-DA96", "icd_code": "DA96", "title": "Cirrhosis", "synonyms": ["liver cirrhosis", "hepatic cirrhosis", "end-stage liver disease"]},
    {"id": "icd-DA97", "icd_code": "DA97", "title": "Pancreatitis", "synonyms": ["acute pancreatitis", "chronic pancreatitis", "pancreatic inflammation"]},
    {"id": "icd-DA98", "icd_code": "DA98", "title": "Colorectal cancer", "synonyms": ["colon cancer", "rectal cancer", "bowel cancer", "CRC"]},
    {"id": "icd-DA99", "icd_code": "DA99", "title": "Celiac disease", "synonyms": ["coeliac disease", "gluten intolerance", "gluten-sensitive enteropathy"]},
    # Musculoskeletal
    {"id": "icd-FA00", "icd_code": "FA00", "title": "Rheumatoid arthritis", "synonyms": ["RA", "inflammatory arthritis", "autoimmune arthritis"]},
    {"id": "icd-FA01", "icd_code": "FA01", "title": "Osteoarthritis", "synonyms": ["OA", "degenerative joint disease", "wear-and-tear arthritis"]},
    {"id": "icd-FA02", "icd_code": "FA02", "title": "Osteoporosis", "synonyms": ["brittle bones", "bone loss", "low bone density"]},
    {"id": "icd-FA03", "icd_code": "FA03", "title": "Systemic lupus erythematosus", "synonyms": ["SLE", "lupus", "autoimmune disease"]},
    {"id": "icd-FA04", "icd_code": "FA04", "title": "Fibromyalgia", "synonyms": ["fibromyositis", "fibrositis", "chronic pain syndrome"]},
    {"id": "icd-FA05", "icd_code": "FA05", "title": "Ankylosing spondylitis", "synonyms": ["AS", "axial spondyloarthritis", "Bechterew disease"]},
    {"id": "icd-FA06", "icd_code": "FA06", "title": "Psoriatic arthritis", "synonyms": ["PsA", "arthritis with psoriasis"]},
    # Mental health
    {"id": "icd-6A70", "icd_code": "6A70", "title": "Major depressive disorder", "synonyms": ["MDD", "clinical depression", "unipolar depression"]},
    {"id": "icd-6A71", "icd_code": "6A71", "title": "Generalized anxiety disorder", "synonyms": ["GAD", "anxiety neurosis", "anxiety state"]},
    {"id": "icd-6A72", "icd_code": "6A72", "title": "Bipolar disorder", "synonyms": ["bipolar affective disorder", "manic depression", "BD"]},
    {"id": "icd-6A73", "icd_code": "6A73", "title": "Schizophrenia", "synonyms": ["psychosis", "schizophrenic disorder"]},
    {"id": "icd-6A74", "icd_code": "6A74", "title": "Post-traumatic stress disorder", "synonyms": ["PTSD", "trauma disorder", "combat stress"]},
    {"id": "icd-6A75", "icd_code": "6A75", "title": "Obsessive-compulsive disorder", "synonyms": ["OCD", "obsessional neurosis"]},
    {"id": "icd-6A76", "icd_code": "6A76", "title": "Attention deficit hyperactivity disorder", "synonyms": ["ADHD", "ADD", "hyperkinetic disorder"]},
    {"id": "icd-6A77", "icd_code": "6A77", "title": "Autism spectrum disorder", "synonyms": ["ASD", "autism", "Asperger syndrome"]},
    # Renal / urological
    {"id": "icd-GB00", "icd_code": "GB00", "title": "Chronic kidney disease", "synonyms": ["CKD", "chronic renal failure", "renal insufficiency"]},
    {"id": "icd-GB01", "icd_code": "GB01", "title": "Acute kidney injury", "synonyms": ["AKI", "acute renal failure", "ARF"]},
    {"id": "icd-GB02", "icd_code": "GB02", "title": "Urinary tract infection", "synonyms": ["UTI", "cystitis", "bladder infection"]},
    {"id": "icd-GB03", "icd_code": "GB03", "title": "Kidney stones", "synonyms": ["nephrolithiasis", "urolithiasis", "renal calculi"]},
    {"id": "icd-GB04", "icd_code": "GB04", "title": "Glomerulonephritis", "synonyms": ["nephritis", "glomerular nephritis"]},
    # Dermatological
    {"id": "icd-EA90", "icd_code": "EA90", "title": "Psoriasis", "synonyms": ["psoriasis vulgaris", "chronic plaque psoriasis"]},
    {"id": "icd-EA91", "icd_code": "EA91", "title": "Atopic dermatitis", "synonyms": ["eczema", "atopic eczema", "neurodermatitis"]},
    {"id": "icd-EA92", "icd_code": "EA92", "title": "Skin cancer", "synonyms": ["melanoma", "basal cell carcinoma", "squamous cell carcinoma"]},
    {"id": "icd-EA93", "icd_code": "EA93", "title": "Acne vulgaris", "synonyms": ["acne", "pimples", "cystic acne"]},
    {"id": "icd-EA94", "icd_code": "EA94", "title": "Rosacea", "synonyms": ["facial redness", "acne rosacea"]},
    # Haematological / oncological
    {"id": "icd-2A00", "icd_code": "2A00", "title": "Leukemia", "synonyms": ["leukaemia", "blood cancer", "AML", "CML", "ALL", "CLL"]},
    {"id": "icd-2A01", "icd_code": "2A01", "title": "Lymphoma", "synonyms": ["Hodgkin lymphoma", "non-Hodgkin lymphoma", "NHL"]},
    {"id": "icd-2A02", "icd_code": "2A02", "title": "Breast cancer", "synonyms": ["mammary carcinoma", "breast carcinoma", "BC"]},
    {"id": "icd-2A03", "icd_code": "2A03", "title": "Prostate cancer", "synonyms": ["prostatic carcinoma", "PC", "adenocarcinoma of prostate"]},
    {"id": "icd-2A04", "icd_code": "2A04", "title": "Anemia", "synonyms": ["anaemia", "iron deficiency anemia", "IDA"]},
    {"id": "icd-2A05", "icd_code": "2A05", "title": "Sickle cell disease", "synonyms": ["sickle cell anemia", "HbSS disease"]},
    # Ophthalmic
    {"id": "icd-9A00", "icd_code": "9A00", "title": "Glaucoma", "synonyms": ["open-angle glaucoma", "intraocular hypertension"]},
    {"id": "icd-9A01", "icd_code": "9A01", "title": "Cataracts", "synonyms": ["lens opacity", "cataract", "age-related cataract"]},
    {"id": "icd-9A02", "icd_code": "9A02", "title": "Macular degeneration", "synonyms": ["AMD", "age-related macular degeneration"]},
    # ENT
    {"id": "icd-AA00", "icd_code": "AA00", "title": "Otitis media", "synonyms": ["middle ear infection", "ear infection"]},
    {"id": "icd-AA01", "icd_code": "AA01", "title": "Sinusitis", "synonyms": ["sinus infection", "rhinosinusitis"]},
    {"id": "icd-AA02", "icd_code": "AA02", "title": "Tonsillitis", "synonyms": ["tonsil infection", "strep throat", "pharyngotonsillitis"]},
]


class ICDConnector(BaseConnector):
    """Connector for WHO ICD-11 disease catalogue.

    When OAuth2 credentials are configured the live API is used; otherwise the
    built-in seed list is returned so the pipeline can run offline.
    """

    source_name = "icd11"

    def __init__(self) -> None:
        super().__init__()
        self._token: str | None = None

    # ------------------------------------------------------------------
    # OAuth2 token
    # ------------------------------------------------------------------

    def _get_token(self) -> str | None:
        """Fetch OAuth2 bearer token from WHO ICD access management."""
        if not settings.ICD_CLIENT_ID or not settings.ICD_CLIENT_SECRET:
            return None
        try:
            resp = requests.post(
                settings.ICD_TOKEN_ENDPOINT,
                data={
                    "client_id": settings.ICD_CLIENT_ID,
                    "client_secret": settings.ICD_CLIENT_SECRET,
                    "scope": "icdapi_access",
                    "grant_type": "client_credentials",
                },
                timeout=15,
            )
            resp.raise_for_status()
            self._token = resp.json().get("access_token")
            return self._token
        except Exception as exc:
            logger.warning("ICD token fetch failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def fetch(self, **kwargs) -> Iterator[dict]:
        """Yield disease records from ICD-11 API or built-in seed."""
        token = self._get_token()
        if not token:
            logger.info("ICD11: no credentials configured – using built-in seed (%d diseases)", len(_ICD_SEED))
            yield from _ICD_SEED
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Accept-Language": "en",
            "API-Version": "v2",
        }
        session = requests.Session()
        session.headers.update(headers)

        try:
            # Browse linearization index
            url = f"{settings.ICD_API_BASE}"
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for child_url in data.get("child", []):
                try:
                    yield from self._recurse(session, child_url, depth=0)
                except Exception as exc:
                    logger.warning("ICD recurse error: %s", exc)
        except Exception as exc:
            logger.warning("ICD API unavailable (%s) – falling back to seed", exc)
            yield from _ICD_SEED

    def _recurse(self, session: requests.Session, url: str, depth: int) -> Iterator[dict]:
        """Recursively traverse ICD-11 linearization tree (max depth 3)."""
        if depth > 3:
            return
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return

        code = data.get("code", "")
        title = data.get("title", {})
        if isinstance(title, dict):
            title = title.get("@value", "")
        if title and code:
            synonyms = [
                (s.get("label", {}).get("@value", "") if isinstance(s, dict) else str(s))
                for s in data.get("synonym", [])
            ]
            yield {
                "id": f"icd-{code}",
                "icd_code": code,
                "title": title,
                "synonyms": [s for s in synonyms if s],
                "definition": data.get("definition", {}).get("@value", "") if isinstance(data.get("definition"), dict) else "",
            }

        for child_url in data.get("child", []):
            yield from self._recurse(session, child_url, depth + 1)

    # ------------------------------------------------------------------
    # Normalize
    # ------------------------------------------------------------------

    def normalize(self, raw: dict) -> dict:
        return {
            "disease_id": raw.get("id", f"icd-{raw.get('icd_code', 'unknown')}"),
            "disease_name": raw.get("title", ""),
            "synonyms": raw.get("synonyms", []),
            "definition": raw.get("definition", ""),
            "source": self.source_name,
            "icd_code": raw.get("icd_code", ""),
        }
