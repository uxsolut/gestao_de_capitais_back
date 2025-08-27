# schemas/requisicoes.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field, ConfigDict, field_validator


# ---------- Enum alinhado ao Postgres (public.tipo_de_acao) ----------
class TipoDeAcao(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"
    PATCH = "PATCH"


# ---------- Request ----------
class RequisicaoRequest(BaseModel):
    """
    Modelo para requisição de processamento (todos os campos obrigatórios).
    """
    id_robo: int = Field(..., description="ID do robô que criou a requisição")
    tipo: TipoDeAcao = Field(..., description="Tipo da operação (BUY, SELL, CLOSE, PATCH)")
    symbol: str = Field(..., description="Símbolo do ativo (ex.: EURUSD)")
    id_tipo_ordem: int = Field(..., description="ID na tabela tipo_de_ordem")

    # Compat: ignore campos extras que clientes antigos ainda possam enviar
    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "id_robo": 123,
                "tipo": "BUY",
                "symbol": "EURUSD",
                "id_tipo_ordem": 2
            }
        },
    )

    @field_validator("id_robo")
    @classmethod
    def validate_id_robo(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("ID do robô deve ser maior que zero")
        return v

    @field_validator("id_tipo_ordem")
    @classmethod
    def validate_id_tipo_ordem(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("id_tipo_ordem deve ser maior que zero")
        return v

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("symbol é obrigatório")
        return v

    # aceita strings em qualquer caixa e converte para o Enum
    @field_validator("tipo", mode="before")
    @classmethod
    def normalize_tipo(cls, v):
        if isinstance(v, str):
            v = v.strip().upper()
        return v


# ---------- Response por conta ----------
class ContaProcessada(BaseModel):
    """Modelo por conta processada na requisição"""
    conta: str = Field(..., description="Identificador da conta (conta_meta_trader)")
    status: str = Field(..., description="Status do processamento para a conta")

    # Informações do token opaco (um token por CONTA)
    token_gerado: bool = Field(..., description="Indica se foi gerado/atualizado token opaco para a conta")
    token: Optional[str] = Field(
        None,
        description="Token opaco (sem prefixo) associado à conta. Pode ser omitido na resposta pública."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conta": "123456789",
                "status": "sucesso",
                "token_gerado": True,
                "token": "abc123..."  # opcional expor
            }
        }
    )


# ---------- Response do processamento ----------
class ProcessamentoResponse(BaseModel):
    """Modelo de resposta para processamento de requisição"""
    id: int
    status: str
    message: str
    contas_processadas: int
    contas_com_erro: int
    detalhes: List[ContaProcessada]
    tempo_processamento: float

    # (Opcional) mapa conta → token cru (sem prefixo)
    tokens_por_conta: Optional[Dict[str, str]] = Field(
        None,
        description="Mapa conta→token opaco (sem prefixo) retornado pelo serviço."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 456,
                "status": "success",
                "message": "Requisição processada e organizada no Redis por conta",
                "contas_processadas": 2,
                "contas_com_erro": 0,
                "detalhes": [
                    {"conta": "123456789", "status": "sucesso", "token_gerado": True, "token": "abc123..."},
                    {"conta": "987654321", "status": "sucesso", "token_gerado": True, "token": "def456..."}
                ],
                "tempo_processamento": 0.125,
                "tokens_por_conta": {
                    "123456789": "abc123...",
                    "987654321": "def456..."
                }
            }
        }
    )


# ---------- Status ----------
class StatusResponse(BaseModel):
    """Modelo de resposta para status de requisição"""
    id: int
    status: str
    contas_encontradas: int
    redis_organizado: bool
    tempo_processamento: float

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 456,
                "status": "processed",
                "contas_encontradas": 2,
                "redis_organizado": True,
                "tempo_processamento": 0.045
            }
        }
    )


# ---------- Health ----------
class HealthResponse(BaseModel):
    """Modelo de resposta para health check"""
    status: str
    timestamp: datetime
    version: str
    services: Dict[str, str]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "timestamp": "2025-01-21T10:30:00",
                "version": "2.0.0",
                "services": {"postgresql": "connected", "redis": "connected"}
            }
        }
    )


# ---------- Error ----------
class ErrorResponse(BaseModel):
    """Modelo de resposta para erros"""
    status: str = "error"
    message: str
    error_code: Optional[str] = None
    correlation_id: Optional[str] = None
    tempo_processamento: Optional[float] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "error",
                "message": "Erro ao processar requisição",
                "error_code": "DATABASE_ERROR",
                "correlation_id": "abc-123-def",
                "tempo_processamento": 0.025
            }
        }
    )
