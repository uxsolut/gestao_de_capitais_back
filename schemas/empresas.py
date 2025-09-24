# schemas/empresas.py
# -*- coding: utf-8 -*-
from typing import Optional
from pydantic import BaseModel, Field

class EmpresaBase(BaseModel):
    nome: str = Field(..., min_length=1)
    descricao: Optional[str] = None
    ramo_de_atividade: Optional[str] = None

class EmpresaOut(EmpresaBase):
    id: int

    class Config:
        from_attributes = True  # pydantic v2 (substitui orm_mode=True)
