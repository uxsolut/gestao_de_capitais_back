# schemas/projeto.py
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class ProjetoBase(BaseModel):
    nome: str
    id_pagina_em_uso: Optional[int] = None

class ProjetoCreate(ProjetoBase):
    pass

class ProjetoUpdate(BaseModel):
    nome: Optional[str] = None
    id_pagina_em_uso: Optional[int] = None

class Projeto(ProjetoBase):
    id: int
    atualizado_em: datetime
    model_config = ConfigDict(from_attributes=True)
