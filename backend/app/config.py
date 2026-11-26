import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Telecalling CRM SaaS"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"
    
    # Database: Supports SQLite (for immediate local dev) or PostgreSQL (production)
    # Default is SQLite file in the project folder; set DATABASE_URL in .env for PostgreSQL
    DATABASE_URL: str = "sqlite:///./crm.db"
    
    # JWT Security
    SECRET_KEY: str = "telecalling-crm-saas-super-secret-key-change-in-production-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 hours
    
    # Telephony Provider Default (mock, exotel, ozonetel, knowlarity, myoperator, twilio)
    TELEPHONY_PROVIDER: str = "mock"
    
    # Uploads & Storage directory
    UPLOAD_DIR: str = "./uploads"

    # Feature Flags
    SUPER_ADMIN_ENABLED: bool = False

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()

# Ensure uploads directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "recordings"), exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "imports"), exist_ok=True)
