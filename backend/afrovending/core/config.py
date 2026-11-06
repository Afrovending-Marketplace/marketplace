import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

APP_NAME = "AfroVending Online Marketplace"
APP_VERSION = "0.13.0-phase13"
API_VERSION = "v1"
CURRENT_PHASE = 9


class Settings:
    def __init__(self) -> None:
        self.mongo_url = os.environ["MONGO_URL"]
        self.db_name = os.environ["DB_NAME"]
        self.app_env = os.environ["APP_ENV"]
        self.log_level = os.environ["LOG_LEVEL"]
        self.frontend_url = os.environ["FRONTEND_URL"].rstrip("/")
        self.jwt_secret = os.environ["JWT_SECRET"]
        self.admin_email = os.environ["ADMIN_EMAIL"].strip().lower()
        self.admin_password = os.environ["ADMIN_PASSWORD"]
        self.contact_inbox = os.environ["CONTACT_INBOX"]
        extra = [o.strip() for o in os.environ["CORS_ORIGINS"].split(",") if o.strip() and o.strip() != "*"]
        self.cors_origins = [self.frontend_url, *extra]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
