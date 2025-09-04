import os
from functools import lru_cache

class Settings:
    api_key: str | None = os.getenv("ELIG_API_KEY")
    admin_key: str | None = os.getenv("ELIG_ADMIN_KEY")
    mock_mode: bool = os.getenv("ELIG_API_MOCK", "0") == "1"
    rate_limit_per_minute: int = int(os.getenv("ELIG_RATE_LIMIT", 60))
    db_path: str = os.getenv("ELIG_DB", "./eligibility.db")

    sam_entity_base: str = os.getenv("SAM_ENTITY_API", "https://api.sam.gov/entity-information/v2/entities")
    sam_exclusions_base: str = os.getenv("SAM_EXCLUSIONS_API", "https://api.sam.gov/exclusions/v2/exclusions")
    sam_api_key: str | None = os.getenv("SAM_API_KEY")

    webhook_sig_key: str | None = os.getenv("ELIG_WEBHOOK_SIG")  # HMAC key for webhook signatures

@lru_cache
def get_settings() -> Settings:
    return Settings()
