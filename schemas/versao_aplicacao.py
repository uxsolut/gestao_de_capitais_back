from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class VersaoAplicacaoBase(BaseModel):
    descricao: str
    id_aplicacao: Optional[int] = None  # ✅ novo campo

class VersaoAplicacaoCreate(VersaoAplicacaoBase):
    pass  # arquivo será recebido via UploadFile no endpoint

class VersaoAplicacao(VersaoAplicacaoBase):
    id: int
    data_versao: Optional[datetime]
    criado_em: Optional[datetime]
    id_user: int

    class Config:
        from_attributes = True
