# Pydantic v1 (se estiver no v2, veja observação no final)
from pydantic import BaseModel
from typing import Optional

class ContaBase(BaseModel):
    # OPCIONAIS
    conta_meta_trader: Optional[str] = None
    id_corretora: Optional[int] = None
    nome: Optional[str] = None
    margem_total: Optional[float] = None
    margem_disponivel: Optional[float] = None
    jwt_atual: Optional[str] = None

class ContaCreate(ContaBase):
    # OBRIGATÓRIO no POST
    id_carteira: int

class ContaUpdate(ContaBase):
    # tudo opcional para PUT/PATCH
    id_carteira: Optional[int] = None

class ContaOut(ContaBase):
    id: int
    id_carteira: Optional[int] = None

    class Config:
        orm_mode = True
