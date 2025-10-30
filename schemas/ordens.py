# schemas/ordens.py
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---- Enums (espelham os tipos do Postgres) -----------------------------------
class OrdemStatus(str, Enum):
    INICIALIZADO = "Inicializado"
    CONSUMIDO = "Consumido"


class TipoDeAcao(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"
    PATCH = "PATCH"


# ---- Schemas -----------------------------------------------------------------
class OrdemCreate(BaseModel):
    """
    Schema de entrada para criação de ordem.
    Os campos com default no banco (status/criado_em) não precisam ser enviados.
    """
    id_robo_user: Optional[int] = Field(default=None, description="FK robos_do_user.id")
    id_user: Optional[int] = Field(default=None, description="FK users.id")
    numero_unico: Optional[str] = None
    conta_meta_trader: Optional[str] = None
    id_tipo_ordem: Optional[int] = Field(default=None, description="FK tipo_de_ordem.id")
    tipo: Optional[TipoDeAcao] = None
    # status e criado_em ficam a cargo do banco (defaults)


class Ordem(BaseModel):
    """
    Schema de saída/retorno de ordem.
    """
    id: int
    id_robo_user: Optional[int] = None
    id_user: Optional[int] = None
    numero_unico: Optional[str] = None
    conta_meta_trader: Optional[str] = None
    status: OrdemStatus
    id_tipo_ordem: Optional[int] = None
    tipo: Optional[TipoDeAcao] = None
    criado_em: datetime

    class Config:
        from_attributes = True
