# 1M Medical Dataset Pipeline

**A production-grade Python pipeline for assembling a 1-million-row medical dataset** combining real clinical ontologies (ICD-11, UMLS), symptom databases, treatment references, and controlled synthetic generation.

> **بالعربية:** خط أنابيب بايثون لبناء مجموعة بيانات طبية تضم مليون سجل، تجمع بين مصادر حقيقية (ICD-11, UMLS, openFDA) وتوليد اصطناعي خاضع للرقابة، مع بوابة جودة بيانات متكاملة.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    CLI  (main.py)                        │
│   ingest │ enrich │ build │ validate │ export │ demo     │
└────────────────────────┬────────────────────────────────┘
                         │
         ┌───────────────▼───────────────┐
         │       DatasetBuilder          │
         │     (pipeline/build_dataset)  │
         └──┬───────────────────────────┘
            │
   ┌────────▼─────────┐    ┌──────────────────────┐
   │  Data Sources    │    │   Processors          │
   │                  │    │                       │
   │ ├ ICD-11         │    │ ├ ProbabilityEngine   │
   │ ├ UMLS           │    │ ├ UrgencyEngine        │
   │ ├ Infermedica    │    │ ├ SyntheticGenerator  │
   │ ├ SymCAT         │    │ └ Normalization utils │
   │ ├ HDSN           │    └──────────────────────┘
   │ ├ MedlinePlus    │
   │ ├ openFDA        │    ┌──────────────────────┐
   │ └ ClinicalTrials │    │   Storage             │
   └──────────────────┘    │   MongoStore          │
                           │   (MongoDB)           │
                           └──────────────────────┘
                                    │
                    ┌───────────────▼──────────────────┐
                    │      Data Quality Gate            │
                    │    (data_quality/validators)      │
                    └───────────────────────────────────┘
```

---

## Installation

```bash
# 1. Clone the repository
git clone <repo-url>
cd datacollector

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Configure API keys
cp .env.example .env
# Edit .env with your credentials
```

### Prerequisites

| Service   | Required? | Notes                                      |
|-----------|-----------|---------------------------------------------|
| MongoDB   | Yes (for `build`, `ingest`, `export`) | `docker run -d -p 27017:27017 mongo` |
| ICD-11 API credentials | No | Falls back to 100-disease seed |
| UMLS API key | No | Falls back to 50-disease seed |
| Infermedica credentials | No | Falls back to built-in mapping |

---

## Configuration (.env)

```dotenv
# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB=medical_dataset

# WHO ICD-11 (optional)
ICD_CLIENT_ID=your_client_id
ICD_CLIENT_SECRET=your_client_secret

# UMLS (optional)
UMLS_API_KEY=your_umls_api_key

# Infermedica (optional)
INFERMEDICA_APP_ID=your_app_id
INFERMEDICA_APP_KEY=your_app_key

# Pipeline settings
TARGET_ROWS=1000000
SYNTHETIC_CAP=0.70
BATCH_SIZE=500
```

---

## Usage

### Demo (no API keys or MongoDB required)

```bash
python main.py demo
python main.py demo --count 5000
```

### Full pipeline

```bash
# Phase 1: Ingest diseases and symptom mappings
python main.py ingest

# Phase 2: Enrich with treatment data
python main.py enrich

# Phase 3: Build full 1M-row dataset
python main.py build --target 1000000

# Validate data quality
python main.py validate --limit 50000

# Show statistics
python main.py stats

# Export to Parquet
python main.py export --output dataset.parquet --limit 500000
```

### Logging verbosity

```bash
python main.py --log-level DEBUG demo
```

---

## Data Schema

Each row in `final_rows` conforms to the `MedicalRecord` model:

| Field            | Type              | Description                                    |
|------------------|-------------------|------------------------------------------------|
| `record_id`      | `str` (UUID)      | Unique record identifier                       |
| `disease_id`     | `str`             | Ontology ID (ICD-11, UMLS CUI, or seed ID)     |
| `disease_name`   | `str`             | Canonical disease name                         |
| `symptoms`       | `list[str]`       | ≥1 symptom strings                             |
| `age_group`      | `enum`            | infant / child / adult / elderly               |
| `gender`         | `enum`            | male / female / other                          |
| `probability`    | `float [0–1]`     | Aggregate symptom-disease probability          |
| `treatment`      | `list[str]`       | Treatment options                              |
| `drugs`          | `list[DrugInfo]`  | Drug name, dose, route                         |
| `urgency`        | `enum`            | low / medium / high / emergency                |
| `source_list`    | `list[str]`       | Data provenance tags                           |
| `confidence_score`| `float [0–1]`   | Record-level confidence                        |
| `is_synthetic`   | `bool`            | True if synthetically generated                |
| `created_at`     | `datetime`        | UTC timestamp                                  |
| `meta`           | `dict`            | Free-form metadata                             |

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## Data Sources & Provenance

| Source | Type | License / Notes |
|--------|------|-----------------|
| WHO ICD-11 | Disease ontology | Creative Commons / requires registration |
| UMLS | Medical concepts | NLM license (free, registration required) |
| Infermedica | Symptom-disease | Commercial API (free tier available) |
| SymCAT | Symptom frequencies | Built-in curated data |
| HDSN | Disease-symptom network | Built-in curated data |
| MedlinePlus | Treatments | Public domain (NLM) |
| openFDA | Drug labels | Public domain (FDA) |
| ClinicalTrials.gov | Trials | Public domain (NIH) |
| Synthetic | Generated | Controlled synthetic (max 70%) |

---

## License

**For research use only.** This pipeline aggregates data from multiple sources with varying licenses. Ensure compliance with the terms of each upstream data source before commercial use.

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request
