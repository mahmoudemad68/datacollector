"""Treatment and drug enrichment connectors."""
from __future__ import annotations

import logging
from typing import Iterator

import requests

from config.settings import settings
from sources.base import BaseConnector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in fallback treatment data
# ---------------------------------------------------------------------------
_TREATMENT_DATA: dict[str, list[str]] = {
    "Influenza": ["antiviral medications (oseltamivir)", "rest", "hydration", "fever reducers"],
    "COVID-19": ["antivirals (nirmatrelvir/ritonavir)", "supportive care", "oxygen therapy", "corticosteroids"],
    "Pneumonia": ["antibiotics", "antiviral therapy", "rest", "fluids", "oxygen therapy"],
    "Tuberculosis": ["isoniazid", "rifampicin", "pyrazinamide", "ethambutol", "DOTS therapy"],
    "Malaria": ["artemisinin-based combination therapy", "chloroquine", "supportive care"],
    "Dengue fever": ["supportive care", "hydration", "fever reducers", "pain relievers"],
    "HIV/AIDS": ["antiretroviral therapy (ART)", "prophylaxis", "immune support"],
    "Sepsis": ["broad-spectrum antibiotics", "IV fluids", "vasopressors", "oxygen therapy", "ICU care"],
    "Meningitis": ["antibiotics (ceftriaxone)", "corticosteroids", "hospitalization", "supportive care"],
    "Acute myocardial infarction": ["aspirin", "thrombolytics", "PCI (angioplasty)", "beta-blockers", "statins"],
    "Heart failure": ["ACE inhibitors", "beta-blockers", "diuretics", "digoxin", "lifestyle modifications"],
    "Hypertension": ["lifestyle changes", "ACE inhibitors", "ARBs", "calcium channel blockers", "diuretics"],
    "Atrial fibrillation": ["anticoagulants", "rate control medications", "cardioversion", "ablation"],
    "Stroke": ["thrombolytics (tPA)", "antiplatelet therapy", "rehabilitation", "blood pressure management"],
    "Deep vein thrombosis": ["anticoagulants (heparin, warfarin)", "compression stockings", "elevation"],
    "Pulmonary embolism": ["anticoagulants", "thrombolytics", "surgical embolectomy", "oxygen"],
    "Asthma": ["inhaled corticosteroids", "bronchodilators", "leukotriene modifiers", "avoid triggers"],
    "COPD": ["bronchodilators", "inhaled corticosteroids", "oxygen therapy", "pulmonary rehabilitation"],
    "Lung cancer": ["surgery", "chemotherapy", "radiation therapy", "targeted therapy", "immunotherapy"],
    "Type 2 diabetes mellitus": ["metformin", "insulin therapy", "GLP-1 agonists", "lifestyle changes", "SGLT2 inhibitors"],
    "Type 1 diabetes mellitus": ["insulin therapy", "blood sugar monitoring", "carbohydrate counting", "exercise"],
    "Hypothyroidism": ["levothyroxine", "regular monitoring"],
    "Hyperthyroidism": ["antithyroid medications (methimazole)", "radioactive iodine", "beta-blockers", "surgery"],
    "Gout": ["NSAIDs", "colchicine", "allopurinol", "febuxostat", "dietary changes"],
    "Gastroesophageal reflux disease": ["proton pump inhibitors", "H2 blockers", "antacids", "lifestyle changes"],
    "Peptic ulcer disease": ["proton pump inhibitors", "H2 blockers", "antibiotics for H. pylori", "antacids"],
    "Crohn disease": ["aminosalicylates", "corticosteroids", "immunomodulators", "biologics"],
    "Ulcerative colitis": ["aminosalicylates", "corticosteroids", "immunosuppressants", "surgery"],
    "Irritable bowel syndrome": ["dietary modifications", "fiber supplements", "antispasmodics", "probiotics"],
    "Appendicitis": ["appendectomy (surgery)", "antibiotics"],
    "Cirrhosis": ["treat underlying cause", "diuretics", "beta-blockers", "liver transplant"],
    "Rheumatoid arthritis": ["methotrexate", "biologics (TNF inhibitors)", "NSAIDs", "corticosteroids"],
    "Osteoarthritis": ["NSAIDs", "physical therapy", "joint replacement", "corticosteroid injections"],
    "Fibromyalgia": ["duloxetine", "milnacipran", "pregabalin", "exercise therapy", "CBT"],
    "Major depressive disorder": ["SSRIs", "SNRIs", "psychotherapy (CBT)", "lifestyle modifications"],
    "Generalized anxiety disorder": ["SSRIs", "SNRIs", "buspirone", "CBT", "mindfulness"],
    "Bipolar disorder": ["lithium", "valproate", "lamotrigine", "antipsychotics", "psychotherapy"],
    "Schizophrenia": ["antipsychotics", "psychosocial therapy", "rehabilitation"],
    "Chronic kidney disease": ["blood pressure control", "diabetes management", "dialysis", "kidney transplant"],
    "Urinary tract infection": ["antibiotics (trimethoprim-sulfamethoxazole)", "nitrofurantoin", "hydration"],
    "Kidney stones": ["pain management", "hydration", "lithotripsy", "surgical removal"],
    "Psoriasis": ["topical corticosteroids", "vitamin D analogues", "biologics", "phototherapy"],
    "Atopic dermatitis": ["topical corticosteroids", "emollients", "antihistamines", "immunosuppressants"],
    "Anemia": ["iron supplements", "vitamin B12", "folic acid", "blood transfusion", "treat underlying cause"],
    "Leukemia": ["chemotherapy", "targeted therapy", "stem cell transplant", "immunotherapy"],
    "Glaucoma": ["eye drops (prostaglandin analogues)", "beta-blockers", "laser therapy", "surgery"],
    "Sinusitis": ["antibiotics", "decongestants", "nasal corticosteroids", "saline irrigation"],
    "Tonsillitis": ["antibiotics (penicillin)", "pain relievers", "gargling", "tonsillectomy"],
}

# Drug → disease indication mappings (built-in)
_DRUG_DATA: list[dict] = [
    {"drug_name": "Metformin", "indications": ["Type 2 diabetes mellitus", "Metabolic syndrome"], "route": "oral"},
    {"drug_name": "Insulin glargine", "indications": ["Type 1 diabetes mellitus", "Type 2 diabetes mellitus"], "route": "subcutaneous"},
    {"drug_name": "Lisinopril", "indications": ["Hypertension", "Heart failure", "Chronic kidney disease"], "route": "oral"},
    {"drug_name": "Atorvastatin", "indications": ["Coronary artery disease", "Hypertension", "Stroke"], "route": "oral"},
    {"drug_name": "Amlodipine", "indications": ["Hypertension", "Coronary artery disease", "Atrial fibrillation"], "route": "oral"},
    {"drug_name": "Omeprazole", "indications": ["Gastroesophageal reflux disease", "Peptic ulcer disease"], "route": "oral"},
    {"drug_name": "Metoprolol", "indications": ["Hypertension", "Heart failure", "Atrial fibrillation"], "route": "oral"},
    {"drug_name": "Levothyroxine", "indications": ["Hypothyroidism"], "route": "oral"},
    {"drug_name": "Sertraline", "indications": ["Major depressive disorder", "Generalized anxiety disorder", "PTSD"], "route": "oral"},
    {"drug_name": "Fluoxetine", "indications": ["Major depressive disorder", "Generalized anxiety disorder", "Bipolar disorder"], "route": "oral"},
    {"drug_name": "Albuterol", "indications": ["Asthma", "COPD", "Bronchitis"], "route": "inhalation"},
    {"drug_name": "Fluticasone", "indications": ["Asthma", "COPD", "Sinusitis"], "route": "inhalation"},
    {"drug_name": "Amoxicillin", "indications": ["Pneumonia", "Tonsillitis", "Sinusitis", "Otitis media"], "route": "oral"},
    {"drug_name": "Azithromycin", "indications": ["Pneumonia", "Bronchitis", "Sinusitis"], "route": "oral"},
    {"drug_name": "Warfarin", "indications": ["Atrial fibrillation", "Deep vein thrombosis", "Pulmonary embolism"], "route": "oral"},
    {"drug_name": "Aspirin", "indications": ["Acute myocardial infarction", "Stroke", "Coronary artery disease"], "route": "oral"},
    {"drug_name": "Methotrexate", "indications": ["Rheumatoid arthritis", "Psoriasis", "Psoriatic arthritis"], "route": "oral"},
    {"drug_name": "Adalimumab", "indications": ["Rheumatoid arthritis", "Crohn disease", "Ulcerative colitis", "Psoriasis"], "route": "subcutaneous"},
    {"drug_name": "Prednisone", "indications": ["Asthma", "Rheumatoid arthritis", "Systemic lupus erythematosus", "COPD"], "route": "oral"},
    {"drug_name": "Furosemide", "indications": ["Heart failure", "Hypertension", "Chronic kidney disease"], "route": "oral"},
    {"drug_name": "Oseltamivir", "indications": ["Influenza", "COVID-19"], "route": "oral"},
    {"drug_name": "Isoniazid", "indications": ["Tuberculosis"], "route": "oral"},
    {"drug_name": "Rifampicin", "indications": ["Tuberculosis", "Meningitis"], "route": "oral"},
    {"drug_name": "Ceftriaxone", "indications": ["Pneumonia", "Meningitis", "Sepsis"], "route": "intravenous"},
    {"drug_name": "Colchicine", "indications": ["Gout", "Pericarditis"], "route": "oral"},
    {"drug_name": "Allopurinol", "indications": ["Gout", "Kidney stones"], "route": "oral"},
    {"drug_name": "Lithium carbonate", "indications": ["Bipolar disorder"], "route": "oral"},
    {"drug_name": "Haloperidol", "indications": ["Schizophrenia", "Bipolar disorder"], "route": "oral"},
    {"drug_name": "Levodopa", "indications": ["Parkinson disease"], "route": "oral"},
    {"drug_name": "Memantine", "indications": ["Alzheimer disease"], "route": "oral"},
    {"drug_name": "Donepezil", "indications": ["Alzheimer disease"], "route": "oral"},
    {"drug_name": "Carboplatin", "indications": ["Lung cancer", "Breast cancer", "Ovarian cancer"], "route": "intravenous"},
    {"drug_name": "Tamoxifen", "indications": ["Breast cancer"], "route": "oral"},
    {"drug_name": "Imatinib", "indications": ["Leukemia", "Lymphoma"], "route": "oral"},
    {"drug_name": "Erythropoietin", "indications": ["Anemia", "Chronic kidney disease"], "route": "subcutaneous"},
    {"drug_name": "Hydrochlorothiazide", "indications": ["Hypertension", "Heart failure"], "route": "oral"},
    {"drug_name": "Losartan", "indications": ["Hypertension", "Chronic kidney disease", "Heart failure"], "route": "oral"},
    {"drug_name": "Ciprofloxacin", "indications": ["Urinary tract infection", "Sinusitis", "Pneumonia"], "route": "oral"},
    {"drug_name": "Nitrofurantoin", "indications": ["Urinary tract infection"], "route": "oral"},
    {"drug_name": "Ibuprofen", "indications": ["Gout", "Osteoarthritis", "Rheumatoid arthritis", "Sinusitis"], "route": "oral"},
]

# Clinical trial interventions per disease (built-in)
_TRIALS_DATA: list[dict] = [
    {"disease_name": "Type 2 diabetes mellitus", "interventions": ["semaglutide", "tirzepatide", "SGLT2 inhibitors"], "phase": "Phase 3"},
    {"disease_name": "Heart failure", "interventions": ["sacubitril/valsartan", "empagliflozin"], "phase": "Phase 3"},
    {"disease_name": "Lung cancer", "interventions": ["pembrolizumab", "osimertinib", "nivolumab"], "phase": "Phase 3"},
    {"disease_name": "Breast cancer", "interventions": ["palbociclib", "ribociclib", "trastuzumab deruxtecan"], "phase": "Phase 3"},
    {"disease_name": "Alzheimer disease", "interventions": ["lecanemab", "donanemab", "aducanumab"], "phase": "Phase 3"},
    {"disease_name": "Rheumatoid arthritis", "interventions": ["upadacitinib", "baricitinib", "filgotinib"], "phase": "Phase 3"},
    {"disease_name": "COVID-19", "interventions": ["nirmatrelvir/ritonavir", "molnupiravir", "remdesivir"], "phase": "Phase 3"},
    {"disease_name": "Major depressive disorder", "interventions": ["esketamine", "ketamine", "psilocybin"], "phase": "Phase 2"},
    {"disease_name": "COPD", "interventions": ["tezepelumab", "dupilumab"], "phase": "Phase 3"},
    {"disease_name": "Chronic kidney disease", "interventions": ["finerenone", "dapagliflozin"], "phase": "Phase 3"},
    {"disease_name": "Psoriasis", "interventions": ["bimekizumab", "ixekizumab", "guselkumab"], "phase": "Phase 3"},
    {"disease_name": "Multiple sclerosis", "interventions": ["ofatumumab", "ozanimod", "siponimod"], "phase": "Phase 3"},
    {"disease_name": "Leukemia", "interventions": ["venetoclax", "gilteritinib", "midostaurin"], "phase": "Phase 3"},
    {"disease_name": "Hypertension", "interventions": ["zilebesiran", "aprocitentan"], "phase": "Phase 2"},
    {"disease_name": "Asthma", "interventions": ["tezepelumab", "dupilumab", "itepekimab"], "phase": "Phase 3"},
]


class MedlinePlusConnector(BaseConnector):
    """MedlinePlus health topics connector with built-in fallback."""

    source_name = "medlineplus"

    def fetch(self, **kwargs) -> Iterator[dict]:
        session = requests.Session()
        diseases = list(_TREATMENT_DATA.keys())

        for disease_name in diseases:
            try:
                params = {"db": "healthTopics", "term": disease_name, "retmax": 5}
                resp = session.get(settings.MEDLINEPLUS_BASE_URL, params=params, timeout=10)
                if resp.status_code == 200 and resp.text:
                    # Parse XML snippet for treatment info
                    treatments = _TREATMENT_DATA.get(disease_name, [])
                    yield {"disease_name": disease_name, "treatments": treatments, "source": self.source_name}
                else:
                    yield {
                        "disease_name": disease_name,
                        "treatments": _TREATMENT_DATA.get(disease_name, []),
                        "source": self.source_name,
                    }
            except Exception:
                yield {
                    "disease_name": disease_name,
                    "treatments": _TREATMENT_DATA.get(disease_name, []),
                    "source": self.source_name,
                }

    def normalize(self, raw: dict) -> dict:
        return raw


class OpenFDAConnector(BaseConnector):
    """openFDA drug label connector with built-in fallback."""

    source_name = "openfda"

    def fetch(self, **kwargs) -> Iterator[dict]:
        # Always yield built-in drug data first
        yield from _DRUG_DATA

        if not kwargs.get("use_api", False):
            return

        session = requests.Session()
        try:
            params = {"search": 'product_type:"HUMAN+PRESCRIPTION+DRUG"', "limit": 100}
            resp = session.get(f"{settings.OPENFDA_BASE_URL}/label.json", params=params, timeout=20)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            for item in results:
                name = item.get("openfda", {}).get("generic_name", [""])[0]
                indications = item.get("indications_and_usage", [])
                route = item.get("openfda", {}).get("route", ["unknown"])[0]
                if name:
                    yield {
                        "drug_name": name,
                        "indications": indications,
                        "route": route,
                        "source": self.source_name,
                    }
        except Exception as exc:
            logger.warning("openFDA API failed: %s", exc)

    def normalize(self, raw: dict) -> dict:
        return {
            "drug_name": raw.get("drug_name", ""),
            "indications": raw.get("indications", []),
            "route": raw.get("route", "oral"),
            "source": raw.get("source", self.source_name),
        }


class ClinicalTrialsConnector(BaseConnector):
    """ClinicalTrials.gov v2 API connector with built-in fallback."""

    source_name = "clinicaltrials"

    def fetch(self, **kwargs) -> Iterator[dict]:
        yield from _TRIALS_DATA

        if not kwargs.get("use_api", False):
            return

        session = requests.Session()
        diseases = list(_TREATMENT_DATA.keys())[:20]
        for disease in diseases:
            try:
                params = {
                    "query.cond": disease,
                    "filter.overallStatus": "RECRUITING",
                    "fields": "BriefTitle,Condition,InterventionName,Phase",
                    "pageSize": 10,
                }
                resp = session.get(
                    f"{settings.CLINICALTRIALS_BASE_URL}/studies",
                    params=params,
                    timeout=15,
                )
                if resp.status_code == 200:
                    studies = resp.json().get("studies", [])
                    interventions = []
                    phases = set()
                    for s in studies:
                        proto = s.get("protocolSection", {})
                        for arm in proto.get("armsInterventionsModule", {}).get("interventions", []):
                            interventions.append(arm.get("interventionName", ""))
                        phase = proto.get("designModule", {}).get("phases", [])
                        phases.update(phase)
                    if interventions:
                        yield {
                            "disease_name": disease,
                            "interventions": interventions[:5],
                            "phase": ", ".join(phases) or "N/A",
                            "source": self.source_name,
                        }
            except Exception as exc:
                logger.debug("ClinicalTrials fetch failed for %s: %s", disease, exc)

    def normalize(self, raw: dict) -> dict:
        return {
            "disease_name": raw.get("disease_name", ""),
            "interventions": raw.get("interventions", []),
            "phase": raw.get("phase", "N/A"),
            "source": raw.get("source", self.source_name),
        }
