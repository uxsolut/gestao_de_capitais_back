"""
Middleware para tratamento centralizado de erros
"""
import logging
import traceback
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from config import settings

# Configurar logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except HTTPException as e:
            logger.warning(
                f"HTTP Exception: {e.status_code} - {e.detail} - Path: {request.url.path}"
            )
            raise e
        except Exception as e:
            logger.error(
                f"Unexpected error: {str(e)} - Path: {request.url.path} - Traceback: {traceback.format_exc()}"
            )
            
            if settings.is_development:
                # Em desenvolvimento, retorna detalhes do erro
                return JSONResponse(
                    status_code=500,
                    content={
                        "detail": "Erro interno do servidor",
                        "error": str(e),
                        "traceback": traceback.format_exc() if settings.DEBUG else None
                    }
                )
            else:
                # Em produção, retorna erro genérico
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Erro interno do servidor"}
                )

