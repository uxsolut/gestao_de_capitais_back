from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class AplicacaoBase(BaseModel):
    nome: str
    tipo: str
    id_versao_aplicacao: Optional[int] = None
    id_projeto: Optional[int] = None

class AplicacaoCreate(AplicacaoBase):
    pass

class Aplicacao(AplicacaoBase):
    id: int
    criado_em: Optional[datetime]
    atualizado_em: Optional[datetime]

    class Config:
        orm_mode = True  # ✅ manter isso para compatibilidade
