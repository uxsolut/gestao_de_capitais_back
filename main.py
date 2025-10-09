# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from prometheus_fastapi_instrumentator import Instrumentator

from dotenv import load_dotenv, find_dotenv
from pathlib import Path
import os
import structlog

from config import settings
from database import engine, Base
from middleware.error_handler import ErrorHandlerMiddleware

# --- Carrega models para garantir os mapeamentos/tabelas --
from models import corretoras  # noqa: F401
from models import robos as m_robos  # noqa: F401
from models import requisicoes as m_requisicao  # noqa: F401
from models import tipo_de_ordem as m_tipo_de_ordem  # noqa: F401
from models import ordens as m_ordens  # noqa: F401
from models import aplicacoes as m_aplicacoes  # noqa: F401
from models import empresas as m_empresas  # noqa: F401
from models import page_meta as m_page_meta

# --- Routers da aplicação ---
from routers import (
    cliente_carteiras,
    robos,
    users,
    robos_do_user,
    ordens,
    corretoras as r_corretoras,
    dashboard,
    cliente_contas,
    health,
)
from routers import aplicacoes  # router de Aplicações
from routers import tipo_de_ordem as r_tipo_de_ordem
from routers import ativos as r_ativos
from routers import analises as r_analises
from routers import empresas as r_empresas
from routers.miniapis import router as miniapis_router
from routers import status_aplicacao  # status da aplicação
from routers import page_meta as r_page_meta

# --- Watchdog (apenas para o modo write) ---
from background.token_watchdog import start_token_watchdog, stop_token_watchdog

# ========= ENV =========
DOTENV_PATH = Path(__file__).with_name(".env")
if DOTENV_PATH.exists():
    load_dotenv(dotenv_path=DOTENV_PATH)
else:
    load_dotenv(find_dotenv())

# ---------- Logging estruturado ----------
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger()

# ---------- Criação das tabelas ----------
Base.metadata.create_all(bind=engine)


def create_app(mode: str = "all") -> FastAPI:
    """
    App SEM qualquer lógica de navegação/fallback.
    Apenas expõe as rotas dos routers e a documentação.
    """
    docs_enabled = mode in ("public", "all", "write", "read")
    docs_url = "/docs" if docs_enabled else None
    openapi_url = "/openapi.json" if docs_enabled else None

    # Se ROOT_PATH=/api no .env, tudo sai sob /api (ex.: /api/empresas, /api/docs)
    root_path = os.getenv("ROOT_PATH", "/processar-requisicao" if mode == "write" else "")

    app = FastAPI(
        title="Meta Trade API",
        version="2.0.0",
        description="API de Gestão de Capitais com segurança via Bearer token (opaque).",
        debug=settings.DEBUG,
        docs_url=docs_url,
        openapi_url=openapi_url,
        root_path=root_path,
        servers=[{"url": root_path or "/"}],
    )

    # Middlewares
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Raiz simples
    @app.get("/")
    def read_root():
        return {"mensagem": "API online com sucesso!", "mode": mode, "root_path": root_path}

    # Health sob /api/v1
    app.include_router(health.router, prefix="/api/v1", tags=["Health"])

    # ----------------- Routers -----------------
    if mode == "write":
        from routers import processamento
        app.include_router(processamento.router, tags=["Processamento"], prefix="/api/v1")

    elif mode == "read":
        from routers import consumo_processamento
        app.include_router(consumo_processamento.router, tags=["Consumo Processamento"])

    elif mode == "public":
        app.include_router(ordens.router)
        app.include_router(robos.router)
        app.include_router(users.router)
        app.include_router(robos_do_user.router)
        app.include_router(cliente_carteiras.router)
        app.include_router(r_corretoras.router)
        app.include_router(dashboard.router)
        app.include_router(cliente_contas.router)
        app.include_router(aplicacoes.router, tags=["Aplicações"])
        app.include_router(miniapis_router)
        app.include_router(r_empresas.router, tags=["Empresas"])
        app.include_router(r_tipo_de_ordem.router, tags=["Tipo de Ordem"])
        app.include_router(r_ativos.router, tags=["Ativos"])
        app.include_router(r_analises.router, tags=["Análises"])
        app.include_router(status_aplicacao.router)
        app.include_router(r_page_meta.router, tags=["Page Meta"])

    elif mode == "all":
        app.include_router(ordens.router)
        app.include_router(robos.router)
        app.include_router(users.router)
        app.include_router(robos_do_user.router)
        app.include_router(cliente_carteiras.router)
        app.include_router(r_corretoras.router)
        app.include_router(dashboard.router)
        app.include_router(cliente_contas.router)
        app.include_router(aplicacoes.router, tags=["Aplicações"])
        app.include_router(miniapis_router)
        app.include_router(r_empresas.router, tags=["Empresas"])
        app.include_router(r_tipo_de_ordem.router, tags=["Tipo de Ordem"])
        app.include_router(r_ativos.router)
        app.include_router(r_analises.router, tags=["Análises"])
        app.include_router(status_aplicacao.router)
        app.include_router(r_page_meta.router, tags=["Page Meta"])

        from routers import processamento, consumo_processamento
        app.include_router(processamento.router, prefix="/api/v1", tags=["Processamento"])
        app.include_router(consumo_processamento.router, tags=["Consumo Processamento"])

    # --------- OpenAPI custom (respeita root_path nos servers) ---------
    if docs_enabled:
        def custom_openapi():
            if app.openapi_schema:
                return app.openapi_schema
            openapi_schema = get_openapi(
                title="Meta Trade API",
                version="2.0.0",
                description="Documentação da API com autenticação Bearer (token opaco ou JWT, conforme endpoint).",
                routes=app.routes,
            )
            openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})
            openapi_schema["components"]["securitySchemes"]["BearerAuth"] = {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "Opaque",
            }
            openapi_schema["security"] = [{"BearerAuth": []}]
            openapi_schema["servers"] = [{"url": root_path or "/"}]
            app.openapi_schema = openapi_schema
            return app.openapi_schema

        app.openapi = custom_openapi

    # Métricas
    Instrumentator().instrument(app).expose(app)

    # Eventos
    @app.on_event("startup")
    async def startup_event():
        logger.info(
            "Iniciando API",
            version=settings.app_version,
            mode=mode,
            watchdog_enabled=getattr(settings, "TOKEN_WATCHDOG_ENABLED", True),
        )
        if mode == "write" and str(getattr(settings, "TOKEN_WATCHDOG_ENABLED", True)).lower() not in ("0", "false", "no"):
            start_token_watchdog(app)

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("Encerrando API", mode=mode)
        if mode == "write" and str(getattr(settings, "TOKEN_WATCHDOG_ENABLED", True)).lower() not in ("0", "false", "no"):
            try:
                stop_token_watchdog(app)
            except Exception:
                pass
        try:
            from database import db_manager
            db_manager.close_connections()
            logger.info("Conexoes de banco fechadas com sucesso")
        except Exception as e:
            logger.error("Erro ao fechar conexoes de banco", error=str(e))

    return app


MODE = os.getenv("APP_MODE", "all")
app = create_app(MODE)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
