# schemas/corretoras.py
from typing import Optional
from pydantic import BaseModel

# ---- Base (somente campos comuns não obrigatórios em entrada) ----
class CorretoraBase(BaseModel):
    nome: str
    cnpj: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None

# ---- Entrada (POST) ----
# pais opcional com default "Brasil" (front pode omitir)
class CorretoraCreate(CorretoraBase):
    pais: Optional[str] = "Brasil"

# ---- Saída (GET/POST response) ----
# pais obrigatório aqui, refletindo NOT NULL do banco
class Corretora(CorretoraBase):
    id: int
    pais: str

    # Pydantic v1
    class Config:
        orm_mode = True

    # Pydantic v2 (se estiver usando)
    # from pydantic import ConfigDict
    # model_config = ConfigDict(from_attributes=True)

# ---- Entrada (PUT/PATCH) ----
# todos os campos opcionais
class CorretoraUpdate(BaseModel):
    nome: Optional[str] = None
    cnpj: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    pais: Optional[str] = None
