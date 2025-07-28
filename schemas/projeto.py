from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ProjetoBase(BaseModel):
    nome: str

class ProjetoCreate(ProjetoBase):
    pass

class Projeto(ProjetoBase):
    id: int
    criado_em: Optional[datetime]
    atualizado_em: Optional[datetime]

    class Config:
        orm_mode = True
