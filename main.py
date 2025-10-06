# main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional, Tuple

from dotenv import load_dotenv, find_dotenv
from pathlib import Path
DOTENV_PATH = Path(__file__).with_name(".env")
if DOTENV_PATH.exists():
    load_dotenv(dotenv_path=DOTENV_PATH)
else:
    load_dotenv(find_dotenv())

import os
import structlog
from urllib.parse import urlsplit, urlunsplit, urlencode, parse_qsl  # já usado

from config import settings
from database import engine, Base
from middleware.error_handler import ErrorHandlerMiddleware

# --- Carrega models para garantir os mapeamentos/tabelas ---
from models import corretoras  # noqa: F401
from models import robos as m_robos  # noqa: F401
from models import requisicoes as m_requisicao  # noqa: F401
from models import tipo_de_ordem as m_tipo_de_ordem  # noqa: F401
from models import ordens as m_ordens  # noqa: F401
from models import aplicacoes as m_aplicacoes  # noqa: F401
from models import empresas as m_empresas  # noqa: F401

# --- Routers "públicos" de app (EXCETO processamento/consumo) ---
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
from routers import status_aplicacao  # <-- ADICIONADO

# --- Watchdog (apenas para o modo write) ---
from background.token_watchdog import start_token_watchdog, stop_token_watchdog

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

# ---------- Fallback helpers (queries encapsuladas) ----------
from services.fallback_helpers import (
    empresa_id_por_slug, precisa_logar, url_login, url_nao_tem
)

# ---------- Criação das tabelas ----------
Base.metadata.create_all(bind=engine)

# ================= Helper de redirect (IGNORA root_path) =================
def _absolute_redirect(
    request: Request,
    target: Optional[str],
    append_next: Optional[str] = None,
) -> str:
    """
    Constrói URL ABSOLUTA para redirect.
    - IGNORA root_path do ASGI scope (mesmo se app foi iniciado com /api).
    - Se 'target' for absoluto (http/https): só anexa ?next=...
    - Se 'target' for relativo: usa esquema/host do request e NÃO prefixa root_path.
    - Também remove root_path do valor enviado em 'next'.
    """
    if not target:
        target = "/"

    # monta 'next' removendo root_path do path atual
    if append_next is not None:
        next_value = append_next
    else:
        ucur = urlsplit(str(request.url))
        path = ucur.path or "/"
        rp = (request.scope.get("root_path") or "").rstrip("/")
        if rp and path.startswith(rp + "/"):
            path = path[len(rp):]  # remove o /api do começo, se houver
        elif rp and path == rp:
            path = "/"
        next_value = path + (f"?{ucur.query}" if ucur.query else "")

    # alvo absoluto: só agrega ?next=...
    if target.startswith(("http://", "https://")):
        u = urlsplit(target)
        qs = dict(parse_qsl(u.query, keep_blank_values=True))
        qs["next"] = next_value
        new_query = urlencode(qs, doseq=True)
        return urlunsplit((u.scheme, u.netloc, u.path, new_query, u.fragment))

    # alvo relativo: NÃO prefixa root_path
    if not target.startswith("/"):
        target = "/" + target

    u = urlsplit(str(request.url))
    new_query = urlencode({"next": next_value}, doseq=True)
    return urlunsplit((u.scheme, u.netloc, target, new_query, ""))
# ========================================================================

# ======== Guards para não mandar ninguém para a API por engano =========
# Substitua a função atual por esta
def _is_api_path(p: str, root_path: str) -> bool:
    """
    Considera 'API/DOCS' somente se, após remover root_path do início do path,
    o caminho começar com /api, /docs ou /openapi.
    Isso evita marcar /api/dev/... (por causa do root_path) como 'API'.
    """
    if not p:
        return False

    rp = (root_path or "").rstrip("/")
    # strip do root_path do começo do path (se houver)
    if rp and p.startswith(rp + "/"):
        p_wo = p[len(rp):]
    elif rp and p == rp:
        p_wo = "/"
    else:
        p_wo = p

    return p_wo.startswith("/api") or p_wo.startswith("/openapi") or p_wo.startswith("/docs")


def _safe_login_path(estado: Optional[str], empresa: Optional[str]) -> str:
    if estado and empresa:
        return f"/{estado}/{empresa}/login"
    if empresa:
        return f"/{empresa}/login"
    return "/login"

def _safe_company_root(estado: Optional[str], empresa: Optional[str]) -> str:
    if estado and empresa:
        return f"/{estado}/{empresa}"
    if empresa:
        return f"/{empresa}"
    return "/"
# ======================================================================

def create_app(mode: str = "all") -> FastAPI:
    docs_enabled = mode in ("public", "all", "write", "read")
    docs_url = "/docs" if docs_enabled else None
    openapi_url = "/openapi.json" if docs_enabled else None

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

# --- DEBUG TEMPORÁRIO (pode remover depois) ---
    # --- DEBUG: simular parse usando um path arbitrário ---
    @app.get("/__debug/parse")
    def __debug_parse(request: Request):
        """
        Use:
          curl -s "http://127.0.0.1:8000/__debug/parse" \
            -H 'Host: gestordecapitais.com' \
            -H 'X-Debug-Path: /dev/pinacle/rota-inexistente'
        """
        # pega domínio preferindo Host do Nginx
        host_hdr = (request.headers.get("host") or "").split(":")[0].lower()
        dominio = host_hdr or (request.url.hostname or "").lower()

        # permite SIMULAR o path
        forced_path = request.headers.get("X-Debug-Path")
        raw_path = forced_path or (request.url.path or "/")

        # remove root_path do começo (mesma regra do parse_url)
        root_path_cfg = (request.scope.get("root_path") or "").rstrip("/")
        if root_path_cfg and raw_path.startswith(root_path_cfg + "/"):
            path = raw_path[len(root_path_cfg):]
        elif root_path_cfg and raw_path == root_path_cfg:
            path = "/"
        else:
            path = raw_path

        parts = [p for p in path.split("/") if p]
        estado = empresa = slug = None
        i = 0
        if len(parts) > 0 and parts[0] in ("dev", "beta"):
            estado = parts[0]; i = 1
        if len(parts) > i:
            empresa = parts[i]; i += 1
        if len(parts) > i:
            slug = parts[i]

        # resolve empresa_id (igual ao fluxo real)
        e_id = empresa_id_por_slug(empresa) if empresa else None

        # tenta pegar a URL de 'nao_tem' exatamente como no 404 handler
        url_fallback = url_nao_tem(dominio=dominio, empresa_id=e_id, estado=estado)

        return {
            "host_header": host_hdr,
            "dominio": dominio,
            "estado": estado,
            "empresa_slug": empresa,
            "empresa_id": e_id,
            "url_nao_tem": url_fallback,
            "path_usado": path,
            "root_path": (request.scope.get("root_path") or "")
        }


    # ===================== FALLBACK SERVER-SIDE =====================
    def parse_url(request: Request) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
        """
        Retorna (dominio, estado, empresa_slug, slug)
        - estado: 'dev'|'beta'|None  (None = producao)
        - empresa_slug: ex.: 'pinacle' ou None
        - slug: APENAS o primeiro segmento após a empresa (ou None)
        Obs.: remove o root_path (ex.: /api) do começo do path antes de analisar.
        """
        # usa Host (se presente) para o domínio “real”
        host_hdr = (request.headers.get("host") or "").split(":")[0].lower()
        dominio = host_hdr or (request.url.hostname or "").lower()

        raw_path = request.url.path or "/"
        root_path_cfg = (request.scope.get("root_path") or "").rstrip("/")

        # remove /api (ou o root_path configurado) do início do path
        if root_path_cfg and raw_path.startswith(root_path_cfg + "/"):
            path = raw_path[len(root_path_cfg):]
        elif root_path_cfg and raw_path == root_path_cfg:
            path = "/"
        else:
            path = raw_path

        parts = [p for p in path.split("/") if p]
        estado = empresa = slug = None
        i = 0
        if len(parts) > 0 and parts[0] in ("dev", "beta"):
            estado = parts[0]
            i = 1
        if len(parts) > i:
            empresa = parts[i]
            i += 1
        if len(parts) > i:
            slug = parts[i]
        return dominio, estado, empresa, slug


    def has_valid_jwt(request: Request) -> bool:
        # Troque por sua verificação real (cookie/Authorization/JWT decode)
        auth = request.headers.get("authorization", "")
        return auth.lower().startswith("bearer ") and len(auth.split()) == 2

    class AuthGateMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # -------------------- BYPASS API/DOCS --------------------
            path = request.url.path
            root_path_local = (request.scope.get("root_path") or "")
            if _is_api_path(path, root_path_local):
                return await call_next(request)
            # ---------------------------------------------------------

            dominio, estado, empresa_slug, leaf = parse_url(request)

            if not empresa_slug:
                return await call_next(request)

            empresa_id = empresa_id_por_slug(empresa_slug)
            if not empresa_id:
                return await call_next(request)

            need = precisa_logar(dominio, empresa_id, estado, leaf)  # helpers já fazem fallback p/ 'producao'
            if need is True and not has_valid_jwt(request):
                login_url = url_login(dominio, empresa_id, estado)  # pode ser None/relativo/absoluto

                # Guard: nunca mande p/ /api,/docs etc.
                root_path_local = request.scope.get("root_path", "") or ""
                if not login_url or _is_api_path(str(login_url), root_path_local):
                    login_url = _safe_login_path(estado, empresa_slug)  # relativo seguro

                # NUNCA anexar ?next no redirecionamento de login
                if isinstance(login_url, str) and login_url.startswith(("http://", "https://")):
                    # URL absoluta vinda do banco → usar como está
                    return RedirectResponse(login_url, status_code=302)
                else:
                    # URL relativa → construir absoluta sem query
                    from urllib.parse import urlsplit, urlunsplit
                    u = urlsplit(str(request.url))
                    path_abs = login_url if str(login_url).startswith("/") else f"/{login_url or ''}"
                    dest_abs = urlunsplit((u.scheme, u.netloc, path_abs, "", ""))
                    return RedirectResponse(dest_abs, status_code=302)

            return await call_next(request)

    app.add_middleware(AuthGateMiddleware)

        # ========= ROOT DA EMPRESA (slug vazio) -> página slug NULL ou 'nao_tem' =========
    def _fallback_estados_local(estado: Optional[str]):
        return [estado, "producao"] if estado in ("dev", "beta") else ["producao"]

    def _url_da_pagina_slug_null(dominio: str, empresa_id: Optional[int], estado: Optional[str]) -> Optional[str]:
        from sqlalchemy import text
        estados = _fallback_estados_local(estado)

        # 1) tenta com empresa_id
        if empresa_id is not None:
            with engine.begin() as conn:
                for est in estados:
                    row = conn.execute(
                        text("""
                            SELECT a.url_completa
                              FROM global.aplicacoes a
                             WHERE a.dominio = :dominio
                               AND a.id_empresa = :empresa_id
                               AND a.estado = CAST(:estado AS global.estado_enum)
                               AND a.slug IS NULL
                             ORDER BY a.id DESC
                             LIMIT 1
                        """),
                        {"dominio": dominio, "empresa_id": empresa_id, "estado": est},
                    ).first()
                    if row and row[0]:
                        return row[0]

        # 2) tenta sem empresa_id (barreira cai)
        with engine.begin() as conn:
            for est in estados:
                row = conn.execute(
                    text("""
                        SELECT a.url_completa
                          FROM global.aplicacoes a
                         WHERE a.dominio = :dominio
                           AND a.id_empresa IS NULL
                           AND a.estado = CAST(:estado AS global.estado_enum)
                           AND a.slug IS NULL
                         ORDER BY a.id DESC
                         LIMIT 1
                    """),
                    {"dominio": dominio, "estado": est},
                ).first()
                if row and row[0]:
                    return row[0]
        return None

    @app.get("/{empresa_slug}", include_in_schema=False)
    @app.get("/{empresa_slug}/", include_in_schema=False)
    @app.get("/{estado}/{empresa_slug}", include_in_schema=False)
    @app.get("/{estado}/{empresa_slug}/", include_in_schema=False)
    async def empresa_root_catcher(request: Request, estado: Optional[str] = None, empresa_slug: Optional[str] = None):
        # BYPASS para paths de API/DOCS
        path = request.url.path
        root_path_local = (request.scope.get("root_path") or "")
        if _is_api_path(path, root_path_local):
            return RedirectResponse(url=_absolute_redirect(request, "/"), status_code=302)

        # Parseia de novo para honrar root_path e Host
        dominio, estado_parsed, empresa_parsed, _ = parse_url(request)
        estado = estado_parsed
        empresa_slug = empresa_parsed

        if not empresa_slug:
            return RedirectResponse(url=_absolute_redirect(request, "/"), status_code=302)

        empresa_id = empresa_id_por_slug(empresa_slug)

        # 1) tenta página com slug NULL (página raiz)
        dest = _url_da_pagina_slug_null(dominio=dominio, empresa_id=empresa_id, estado=estado)

        # 2) se não houver, cai no 'nao_tem' (mesmo fluxo do 404)
        if not dest:
            dest = url_nao_tem(dominio=dominio, empresa_id=empresa_id, estado=estado)
            if not dest:
                dest = _safe_company_root(estado, empresa_slug)

        # 3) redireciona
        if isinstance(dest, str) and dest.startswith(("http://", "https://")):
            return RedirectResponse(dest, status_code=302)
        return RedirectResponse(_absolute_redirect(request, dest), status_code=302)
    # =================== FIM ROOT DA EMPRESA ===================


    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        # -------------------- BYPASS API/DOCS --------------------
        path = request.url.path
        root_path_local = (request.scope.get("root_path") or "")
        if _is_api_path(path, root_path_local):
            # Mantém docs funcionando
            return RedirectResponse(url=_absolute_redirect(request, "/"), status_code=302)
        # ---------------------------------------------------------

        dominio, estado, empresa_slug, _ = parse_url(request)

        # sem empresa no path -> manda pro /
        if not empresa_slug:
            return RedirectResponse(url=_absolute_redirect(request, "/"), status_code=302)

        # >>> NÃO FAÇA early return se empresa_id for None <<<
        empresa_id = empresa_id_por_slug(empresa_slug)

        # Usa SEMPRE a URL de 'nao_tem' do banco (aceita empresa_id=None e faz fallback de estado)
        dest = url_nao_tem(dominio=dominio, empresa_id=empresa_id, estado=estado)
        if not dest:
            # fallback simpático: root da empresa/estado
            dest = _safe_company_root(estado, empresa_slug)

        # Se o banco já trouxe URL ABSOLUTA, não anexa ?next=...
        if isinstance(dest, str) and dest.startswith(("http://", "https://")):
            return RedirectResponse(dest, status_code=302)

        # Caso seja RELATIVA, constrói absoluto e anexa ?next=...
        return RedirectResponse(_absolute_redirect(request, dest), status_code=302)


    # =================== FIM FALLBACK SERVER-SIDE ===================

    @app.get("/")
    def read_root():
        return {"mensagem": "API online com sucesso!", "mode": mode, "root_path": root_path}

    app.include_router(health.router, prefix="/api/v1", tags=["Health"])

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
        app.include_router(status_aplicacao.router)  # <-- ADICIONADO

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
        app.include_router(status_aplicacao.router)  # <-- ADICIONADO

        from routers import processamento, consumo_processamento
        app.include_router(processamento.router, prefix="/api/v1", tags=["Processamento"])
        app.include_router(consumo_processamento.router, tags=["Consumo Processamento"])

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

    Instrumentator().instrument(app).expose(app)

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
