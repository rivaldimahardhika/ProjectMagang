import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()

from utils.env_helper import ensure_encryption_key

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///gudang.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY", "please-change-this-in-prod")
    FLASK_ENV = os.getenv("FLASK_ENV", "production")

    ENCRYPTION_KEY = ensure_encryption_key()
