# middleware/navigation_guard.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse, Response
from starlette.requests import Request

# Prefixos que DEVEM ser ignorados pelo middleware de navegação
BYPASS_PREFIXES = (
    "/api", "/docs", "/redoc", "/openapi.json",
    "/metrics", "/health", "/favicon.ico", "/static", "/assets",
)

class NavigationGuardMiddleware(BaseHTTPMiddleware):
    """
    Intercepta SOMENTE as rotas da SPA (fallback) para aplicar
    sua lógica de navegação (domínio/estado/empresa/slug).
    Tudo que começar com BYPASS_PREFIXES passa reto.
    """
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 1) Se for API/Docs/estático → segue direto, nada de navegação aqui
        if path.startswith(BYPASS_PREFIXES):
            return await call_next(request)

        # 2) Aqui é só FRONTEND (SPA). Aplique sua lógica de navegação:
        #    - valida estado
        #    - valida domínio/empresa
        #    - resolve slug, etc.
        #
        # Exemplo de redirecionamento simples (ajuste para sua regra real):
        # if precisa_login(path) and not autenticado(request):
        #     return RedirectResponse(url=f"/?next={path}", status_code=302)
        #
        # Caso contrário, deixe passar para o fallback do frontend:
        return await call_next(request)
