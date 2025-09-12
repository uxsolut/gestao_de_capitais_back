# schemas/tipo_de_ordem.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class NettingOuHedging(str, Enum):
    Netting = "Netting"
    Hedging = "Hedging"


# ------- Base (entrada/edição) -------
class TipoDeOrdemBase(BaseModel):
    nome_da_funcao: str = Field(..., min_length=1, description="Nome único da função")
    codigo_fonte: str = Field(..., description="Código-fonte associado")
    ids_robos: List[int] = Field(default_factory=list, description="IDs de robôs relacionados")
    netting_ou_hedging: NettingOuHedging = Field(..., description="Estratégia (Netting/Hedging)")


# ------- Create -------
class TipoDeOrdemCreate(TipoDeOrdemBase):
    pass


# ------- Response -------
class TipoDeOrdem(TipoDeOrdemBase):
    id: int
    criado_em: datetime

    class Config:
        from_attributes = True  # Pydantic v2: ler de objetos ORM
