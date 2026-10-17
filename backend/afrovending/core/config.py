import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

APP_NAME = "AfroVending Online Marketplace"
APP_VERSION = "0.1.0-phase01"
API_VERSION = "v1"
CURRENT_PHASE = 1


class Settings:
    def __init__(self) -> None:
        self.mongo_url = os.environ["MONGO_URL"]
        self.db_name = os.environ["DB_NAME"]
        self.app_env = os.environ["APP_ENV"]
        self.log_level = os.environ["LOG_LEVEL"]
        self.cors_origins = [o.strip() for o in os.environ["CORS_ORIGINS"].split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
