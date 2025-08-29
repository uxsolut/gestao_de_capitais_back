# schemas/robo.py
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

# -------------------------------------------------
# Versão "canônica" (singular) usada internamente
# -------------------------------------------------
class RoboBase(BaseModel):
    nome: str = Field(..., min_length=1)
    performance: Optional[List[str]] = None
    id_ativo: Optional[int] = None  # FK opcional para ativos.id

class RoboCreate(RoboBase):
    pass

class RoboUpdate(BaseModel):
    # útil se depois quiser PATCH/PUT parcial
    nome: Optional[str] = Field(None, min_length=1)
    performance: Optional[List[str]] = None
    id_ativo: Optional[int] = None

class RoboOut(RoboBase):
    id: int
    criado_em: datetime

    # Pydantic v2
    model_config = ConfigDict(from_attributes=True)

# -------------------------------------------------
# ALIASES para compatibilidade com nomes antigos
# (evita quebrar imports existentes no projeto)
# -------------------------------------------------
RobosBase = RoboBase
RobosCreate = RoboCreate
Robos = RoboOut
