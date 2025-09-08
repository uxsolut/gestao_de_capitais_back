# config.py
import os
from typing import Optional, List
from sqlalchemy.engine.url import make_url
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ==================== Básico ==================== #
    APP_NAME: str = "API POST - Processamento de Requisições"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Modo do app: "write" (só POST + watchdog) | "all" (todas as rotas)
    APP_MODE: str = os.getenv("APP_MODE", "all")

    # ==================== Segurança ==================== #
    SECRET_KEY: str = os.getenv("SECRET_KEY", "sua_chave_secreta_super_segura_aqui")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # Identidade usada para auditoria quando o ator é o sistema (role=system)
    SYSTEM_USER_ID: int = int(os.getenv("SYSTEM_USER_ID", "1"))

    # Namespaces para tokens em Redis
    SYSTEM_TOKEN_NAMESPACE: str = os.getenv("SYSTEM_TOKEN_NAMESPACE", "sys:tok")
    OPAQUE_TOKEN_NAMESPACE: str = os.getenv("OPAQUE_TOKEN_NAMESPACE", "tok")

    # ==================== Banco de Dados (PostgreSQL) ==================== #
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/dbname")

    @property
    def postgres_host(self) -> str:
        return make_url(self.DATABASE_URL).host

    @property
    def postgres_port(self) -> int:
        return make_url(self.DATABASE_URL).port

    @property
    def postgres_db(self) -> str:
        return make_url(self.DATABASE_URL).database

    @property
    def postgres_user(self) -> str:
        return make_url(self.DATABASE_URL).username

    @property
    def postgres_password(self) -> str:
        return make_url(self.DATABASE_URL).password

    # ==================== Redis ==================== #
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")

    @property
    def redis_host(self) -> str:
        if self.REDIS_URL:
            return make_url(self.REDIS_URL).host
        return os.getenv("REDIS_HOST", "localhost")

    @property
    def redis_port(self) -> int:
        if self.REDIS_URL:
            return make_url(self.REDIS_URL).port
        return int(os.getenv("REDIS_PORT", "6379"))

    @property
    def redis_db(self) -> int:
        if self.REDIS_URL:
            db = make_url(self.REDIS_URL).database
            return int(db or 0)
        return int(os.getenv("REDIS_DB", "1"))  # use 1 para dados da app (e 0 p/ tokens)

    @property
    def redis_password(self) -> Optional[str]:
        if self.REDIS_URL:
            return make_url(self.REDIS_URL).password
        return os.getenv("REDIS_PASSWORD")

    # DB global do Redis para tokens opacos
    REDIS_DB_GLOBAL: int = int(os.getenv("REDIS_DB_GLOBAL", "0"))

    # ==================== Watchdog / Tokens Opacos ==================== #
    TOKEN_TTL_SECONDS: int = int(os.getenv("TOKEN_TTL_SECONDS", "300"))  # 5 min
    TOKEN_WATCHDOG_ENABLED: bool = os.getenv("TOKEN_WATCHDOG_ENABLED", "true").lower() not in ("0", "false", "no")
    TOKEN_ROTATE_THRESHOLD_MS: int = int(os.getenv("TOKEN_ROTATE_THRESHOLD_MS", "3000"))
    TOKEN_GRACE_MS: int = int(os.getenv("TOKEN_GRACE_MS", "2000"))
    TOKEN_WATCHDOG_INTERVAL_MS: int = int(os.getenv("TOKEN_WATCHDOG_INTERVAL_MS", "1000"))

    # ==================== Rate Limiting ==================== #
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))

    # ==================== CORS ==================== #
    CORS_ORIGINS: List[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:56166").split(",")
        if origin.strip()
    ]

    # ==================== Deploy de Páginas (opcional) ==================== #
    # Estes campos apareceram no log como “extra inputs”. Incluí para compat.
    BASE_UPLOADS_DIR: Optional[str] = os.getenv("BASE_UPLOADS_DIR")
    BASE_UPLOADS_URL: Optional[str] = os.getenv("BASE_UPLOADS_URL")

    GITHUB_OWNER: Optional[str] = os.getenv("GITHUB_OWNER")
    GITHUB_REPO: Optional[str] = os.getenv("GITHUB_REPO")
    GITHUB_REF: Optional[str] = os.getenv("GITHUB_REF")
    WORKFLOW_FILE: Optional[str] = os.getenv("WORKFLOW_FILE")
    GITHUB_TOKEN_PAGES: Optional[str] = os.getenv("GITHUB_TOKEN_PAGES")
    BASE_URL_MAP_JSON: Optional[str] = os.getenv("BASE_URL_MAP_JSON")

    # ---------- Aliases em minúsculo (compatibilidade) ---------- #
    @property
    def app_name(self) -> str:
        return self.APP_NAME

    @property
    def app_version(self) -> str:
        return self.APP_VERSION

    @property
    def debug(self) -> bool:
        return self.DEBUG

    @property
    def log_level(self) -> str:
        return self.LOG_LEVEL

    @property
    def secret_key(self) -> str:
        return self.SECRET_KEY

    @property
    def algorithm(self) -> str:
        return self.ALGORITHM

    # aliases para os campos de páginas
    @property
    def base_uploads_dir(self) -> Optional[str]:
        return self.BASE_UPLOADS_DIR

    @property
    def base_uploads_url(self) -> Optional[str]:
        return self.BASE_UPLOADS_URL

    @property
    def github_owner(self) -> Optional[str]:
        return self.GITHUB_OWNER

    @property
    def github_repo(self) -> Optional[str]:
        return self.GITHUB_REPO

    @property
    def github_ref(self) -> Optional[str]:
        return self.GITHUB_REF

    @property
    def workflow_file(self) -> Optional[str]:
        return self.WORKFLOW_FILE

    @property
    def github_token_pages(self) -> Optional[str]:
        return self.GITHUB_TOKEN_PAGES

    @property
    def base_url_map_json(self) -> Optional[str]:
        return self.BASE_URL_MAP_JSON

    # ---------- Aliases esperados pelo middleware ---------- #
    @property
    def is_development(self) -> bool:
        # considera dev se ENVIRONMENT=development OU DEBUG=True
        return self.ENVIRONMENT.lower() == "development" or self.DEBUG is True

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    # ---------- Config Pydantic v2 ---------- #
    model_config = SettingsConfigDict(
        env_file="/opt/app/api/.env",      # ajuste se seu .env estiver em outro lugar
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",                    # <- chave para não quebrar com variáveis extras
    )


# Instância global
settings = Settings()
