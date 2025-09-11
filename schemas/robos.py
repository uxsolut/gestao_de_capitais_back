# schemas/robo.py
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator

# --------------------------------------------------------------------
# CREATE (LEGADO) em JSON – /robos/json (sem arquivo) | campos opcionais
# --------------------------------------------------------------------
class RoboCreateJSON(BaseModel):
    nome: str = Field(..., min_length=1)
    performance: Optional[List[str]] = None
    id_ativo: Optional[int] = None

    @field_validator("performance")
    @classmethod
    def _val_performance(cls, v: Optional[List[str]]):
        if v is None:
            return v
        if any(not isinstance(x, str) for x in v):
            raise ValueError("O campo 'performance' deve conter apenas strings.")
        return v


# --------------------------------------------------------------------
# UPDATE parcial (útil para PATCH/PUT)
# --------------------------------------------------------------------
class RoboUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=1)
    performance: Optional[List[str]] = None
    id_ativo: Optional[int] = None

    @field_validator("performance")
    @classmethod
    def _val_performance_update(cls, v: Optional[List[str]]):
        if v is None:
            return v
        if any(not isinstance(x, str) for x in v):
            raise ValueError("O campo 'performance' deve conter apenas strings.")
        return v


# --------------------------------------------------------------------
# READ / OUT – não retornamos o binário; apenas um indicador
# --------------------------------------------------------------------
class RoboOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    criado_em: datetime
    performance: Optional[List[str]] = None
    id_ativo: Optional[int] = None
    tem_arquivo: bool = False  # True se arquivo_robo tiver conteúdo


class RoboOutList(BaseModel):
    itens: List[RoboOut]


# --------------------------------------------------------------------
# ALIASES p/ compatibilidade com importações antigas
# --------------------------------------------------------------------
RoboBase = RoboCreateJSON
RoboCreate = RoboCreateJSON
RobosBase = RoboCreateJSON
RobosCreate = RoboCreateJSON
Robos = RoboOut
