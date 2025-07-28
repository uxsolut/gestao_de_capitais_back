from typing import List
from pydantic import BaseModel
from schemas.contas import Conta  # importa o schema já pronto

class CarteiraBase(BaseModel):
    nome: str

class CarteiraCreate(CarteiraBase):
    pass

class Carteira(CarteiraBase):
    id: int
    id_user: int
    contas: List[Conta] = []  # ✅ novo: lista de contas associadas

    class Config:
        orm_mode = True
