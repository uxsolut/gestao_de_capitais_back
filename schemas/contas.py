from pydantic import BaseModel
from typing import Optional

class ContaBase(BaseModel):
    conta_meta_trader: Optional[str] = None
    id_corretora: Optional[int] = None
    nome: Optional[str] = None

class ContaCreate(ContaBase):
    id_carteira: int  # ✅ obrigatório no POST para vincular a carteira

class Conta(ContaBase):
    id: int
    id_carteira: Optional[int] = None  # ✅ aparece na resposta, mas pode ser null
    margem_total: Optional[float] = None
    margem_disponivel: Optional[float] = None

    class Config:
        orm_mode = True
