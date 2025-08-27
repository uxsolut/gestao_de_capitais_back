from fastapi import APIRouter, Security, HTTPException, status, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, Union
import structlog

from schemas.requisicoes import (
    RequisicaoRequest, ProcessamentoResponse, ErrorResponse
)
from services.processamento_service import ProcessamentoService
from auth.system_auth import get_system_actor  # valida token opaco com role=system

logger = structlog.get_logger()
router = APIRouter()

processamento_service = ProcessamentoService()

@router.post(
    "/processar-requisicao",
    response_model=Union[ProcessamentoResponse, ErrorResponse],
    summary="Processar Nova Requisição (protegido por token opaco de sistema)",
    description=(
        "Processa uma nova requisição de robô e organiza no Redis por conta. "
        "Protegido por **token opaco** com `role=system` (sem login de usuário)."
    ),
)
async def processar_requisicao(
    requisicao: RequisicaoRequest,
    request: Request,
    system_ctx: Dict[str, Any] = Security(get_system_actor),  # valida Bearer do sistema
):
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    try:
        logger.info(
            "Processamento de requisicao recebido",
            correlation_id=correlation_id,
            id_robo=requisicao.id_robo,
            # garante string mesmo que seja Enum
            tipo=(requisicao.tipo.value if hasattr(requisicao.tipo, "value") else str(requisicao.tipo)),
            actor=system_ctx.get("role"),
        )

        # >>> v2: produz dict pronto pra JSON (Enum -> value) e sem None
        dados_req: Dict[str, Any] = requisicao.model_dump(mode="json", exclude_none=True)

        resultado = await processamento_service.processar_requisicao(
            dados_req, system_ctx
        )

        if isinstance(resultado, ErrorResponse):
            if getattr(resultado, "error_code", None) == "NO_ACCOUNTS_FOUND":
                status_code = status.HTTP_404_NOT_FOUND
            else:
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        else:
            status_code = status.HTTP_200_OK

        return JSONResponse(
            status_code=status_code,
            # v2: usa model_dump para serializar corretamente
            content=(resultado.model_dump(mode="json") if hasattr(resultado, "model_dump") else resultado.dict()),
        )

    except HTTPException as http_exc:
        logger.warning(
            "Erro HTTP no processamento",
            correlation_id=correlation_id,
            id_robo=requisicao.id_robo,
            status_code=http_exc.status_code,
            detail=str(http_exc.detail),
        )
        raise

    except Exception as e:
        logger.error(
            "Erro nao tratado no processamento",
            correlation_id=correlation_id,
            id_robo=requisicao.id_robo,
            error=str(e),
        )

        error_response = ErrorResponse(
            message="Erro interno do servidor",
            error_code="UNHANDLED_ERROR",
            correlation_id=correlation_id,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response.model_dump(mode="json"),
        )
