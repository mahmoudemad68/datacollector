"""Application settings loaded from environment / .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Medical Dataset Pipeline."""

    # MongoDB
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB: str = "medical_dataset"

    # WHO ICD-11
    ICD_API_BASE: str = "https://id.who.int/icd/release/11/2024-01/mms"
    ICD_TOKEN_ENDPOINT: str = "https://icdaccessmanagement.who.int/connect/token"
    ICD_CLIENT_ID: str = ""
    ICD_CLIENT_SECRET: str = ""

    # UMLS
    UMLS_API_KEY: str = ""
    UMLS_BASE_URL: str = "https://uts-ws.nlm.nih.gov/rest"

    # Infermedica
    INFERMEDICA_APP_ID: str = ""
    INFERMEDICA_APP_KEY: str = ""
    INFERMEDICA_BASE_URL: str = "https://api.infermedica.com/v3"

    # openFDA
    OPENFDA_BASE_URL: str = "https://api.fda.gov/drug"

    # ClinicalTrials.gov
    CLINICALTRIALS_BASE_URL: str = "https://clinicaltrials.gov/api/v2"

    # MedlinePlus
    MEDLINEPLUS_BASE_URL: str = "https://wsearch.nlm.nih.gov/ws/query"

    # Pipeline behaviour
    BATCH_SIZE: int = 500
    MAX_RETRIES: int = 3
    RETRY_WAIT_SECONDS: float = 2.0
    RATE_LIMIT_CALLS: int = 10
    RATE_LIMIT_PERIOD: float = 1.0

    # Dataset targets
    SYNTHETIC_CAP: float = 0.70
    TARGET_ROWS: int = 1_000_000
    SYMPTOM_MIN: int = 2
    SYMPTOM_MAX: int = 10

    # Logging
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
