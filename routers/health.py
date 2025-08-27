from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from schemas.requisicoes import HealthResponse
from database import db_manager
from config import settings
from datetime import datetime
import structlog

logger = structlog.get_logger()
router = APIRouter()

@router.get("/health",
            response_model=HealthResponse,
            summary="Health Check",
            description="Verifica a saúde da aplicação e suas dependências")
async def health_check():
    """
    Endpoint de health check que verifica:
    - Status da aplicação
    - Conectividade com PostgreSQL
    - Conectividade com Redis
    - Timestamp atual
    - Versão da aplicação
    """
    services_status = {}
    overall_status = "healthy"
    
    try:
        # Testa PostgreSQL
        try:
            with db_manager.get_postgres_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
            services_status["postgresql"] = "connected"
        except Exception as e:
            services_status["postgresql"] = f"error: {str(e)}"
            overall_status = "unhealthy"
            logger.error("PostgreSQL health check failed", error=str(e))
        
        # Testa Redis
        try:
            redis_client = db_manager.get_redis_client()
            redis_client.ping()
            services_status["redis"] = "connected"
        except Exception as e:
            services_status["redis"] = f"error: {str(e)}"
            overall_status = "unhealthy"
            logger.error("Redis health check failed", error=str(e))
        
        # Monta resposta
        health_response = HealthResponse(
            status=overall_status,
            timestamp=datetime.utcnow(),
            version=settings.app_version,
            services=services_status
        )
        
        # Define status HTTP baseado na saúde
        status_code = status.HTTP_200_OK if overall_status == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
        
        logger.info("Health check executado", status=overall_status, services=services_status)
        
        return JSONResponse(
            status_code=status_code,
            content=health_response.dict()
        )
        
    except Exception as e:
        logger.error("Erro no health check", error=str(e))
        
        error_response = HealthResponse(
            status="error",
            timestamp=datetime.utcnow(),
            version=settings.app_version,
            services={"error": str(e)}
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response.dict()
        )

