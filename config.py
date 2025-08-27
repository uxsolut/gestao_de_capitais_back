# config.py
import os
from pydantic_settings import BaseSettings
from sqlalchemy.engine.url import make_url
from typing import Optional, List


class Settings(BaseSettings):
    # ==================== Informações básicas ==================== #
    APP_NAME: str = "API POST - Processamento de Requisições"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")  # Maiúsculo para compatibilidade
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Modo do app: "write" (só POST + watchdog) | "all" (todas as rotas)
    APP_MODE: str = os.getenv("APP_MODE", "all")

    # ==================== Segurança ==================== #
    SECRET_KEY: str = os.getenv("SECRET_KEY", "sua_chave_secreta_super_segura_aqui")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # Identidade usada para auditoria quando o ator é o sistema (role=system)
    SYSTEM_USER_ID: int = int(os.getenv("SYSTEM_USER_ID", "1"))

    # Namespace das chaves de token de sistema no Redis (ex.: sys:tok:<token>)
    SYSTEM_TOKEN_NAMESPACE: str = os.getenv("SYSTEM_TOKEN_NAMESPACE", "sys:tok")

    # Namespace das chaves de token opaco por ordem/conta (ex.: tok:<token>)
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
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL", None)

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

    # DB global do Redis para tokens opacos (separado do redis_db da aplicação)
    REDIS_DB_GLOBAL: int = int(os.getenv("REDIS_DB_GLOBAL", "0"))

    # ==================== Watchdog / Tokens Opacos ==================== #
    # TTL base dos tokens opacos (segundos)
    TOKEN_TTL_SECONDS: int = int(os.getenv("TOKEN_TTL_SECONDS", "300"))  # 5 min
    # Liga/desliga o watchdog
    TOKEN_WATCHDOG_ENABLED: bool = os.getenv("TOKEN_WATCHDOG_ENABLED", "true").lower() not in ("0", "false", "no")
    # Quando rotacionar (ms restantes <= threshold)
    TOKEN_ROTATE_THRESHOLD_MS: int = int(os.getenv("TOKEN_ROTATE_THRESHOLD_MS", "3000"))
    # Janela de graça após a troca (ms)
    TOKEN_GRACE_MS: int = int(os.getenv("TOKEN_GRACE_MS", "2000"))
    # Frequência do loop do watchdog (ms)
    TOKEN_WATCHDOG_INTERVAL_MS: int = int(os.getenv("TOKEN_WATCHDOG_INTERVAL_MS", "1000"))

    # ==================== Rate Limiting ==================== #
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))

    # ==================== CORS ==================== #
    CORS_ORIGINS: List[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://localhost:56166"
        ).split(",")
        if origin.strip()
    ]

    # ---------- Aliases em minúsculo para compatibilidade ---------- #
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

    # ---------- ✅ Aliases esperados pelo middleware ---------- #
    @property
    def is_development(self) -> bool:
        # considera dev se ENVIRONMENT=development OU DEBUG=True
        return self.ENVIRONMENT.lower() == "development" or self.DEBUG is True

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    class Config:
        env_file = ".env"


# Instância global
settings = Settings()
