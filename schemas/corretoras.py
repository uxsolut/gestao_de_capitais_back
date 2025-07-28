from pydantic import BaseModel
from typing import Optional

# Schema base compartilhado entre entrada e saída
class CorretoraBase(BaseModel):
    nome: str
    cnpj: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None

# Schema usado no POST (entrada) — sem id
class CorretoraCreate(CorretoraBase):
    pass

# Schema usado no GET ou POST response — com id
class Corretora(CorretoraBase):
    id: int

    class Config:
        orm_mode = True

        # Schema usado no PUT (atualização) — todos os campos opcionais
class CorretoraUpdate(BaseModel):
    nome: Optional[str] = None
    cnpj: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None

