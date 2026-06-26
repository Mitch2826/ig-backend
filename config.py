import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class BaseConfig:
    # ── Flask core ───────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    DEBUG = False
    TESTING = False

    # ── Database ─────────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,   # avoids stale connection errors with Supabase
        "pool_recycle": 280,     # recycle before Supabase's connection timeout
    }

    # ── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # ── JWT ──────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_TOKEN_LOCATION = ["headers"]

    # ── CORS — only allow the frontend domain ───────────────────────────────
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

    # ── Flask-Smorest / OpenAPI docs ─────────────────────────────────────────
    API_TITLE = "I&G API"
    API_VERSION = "v1"
    OPENAPI_VERSION = "3.0.3"
    OPENAPI_URL_PREFIX = "/"
    OPENAPI_SWAGGER_UI_PATH = "/docs"
    OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

    # ── Cloudinary ────────────────────────────────────────────────────────────
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")

    # ── Daraja (M-Pesa) ───────────────────────────────────────────────────────
    DARAJA_ENV = os.environ.get("DARAJA_ENV", "sandbox")
    DARAJA_CONSUMER_KEY = os.environ.get("DARAJA_CONSUMER_KEY")
    DARAJA_CONSUMER_SECRET = os.environ.get("DARAJA_CONSUMER_SECRET")
    DARAJA_SHORTCODE = os.environ.get("DARAJA_SHORTCODE")
    DARAJA_PASSKEY = os.environ.get("DARAJA_PASSKEY")
    DARAJA_CALLBACK_URL = os.environ.get("DARAJA_CALLBACK_URL")

    # ── iPay / Pesapal ────────────────────────────────────────────────────────
    IPAY_ENV = os.environ.get("IPAY_ENV", "sandbox")
    IPAY_VENDOR_ID = os.environ.get("IPAY_VENDOR_ID")
    IPAY_HASH_KEY = os.environ.get("IPAY_HASH_KEY")
    IPAY_CALLBACK_URL = os.environ.get("IPAY_CALLBACK_URL")

    # ── Email ─────────────────────────────────────────────────────────────────
    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 2525))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@iandg.co.ke")
    MAIL_USE_TLS = True

    # ── SMS (Africa's Talking) ───────────────────────────────────────────────
    AT_USERNAME = os.environ.get("AT_USERNAME", "sandbox")
    AT_API_KEY = os.environ.get("AT_API_KEY")

    # ── Sentry ────────────────────────────────────────────────────────────────
    SENTRY_DSN = os.environ.get("SENTRY_DSN")


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class ProductionConfig(BaseConfig):
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}