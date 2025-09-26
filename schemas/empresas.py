# schemas/empresas.py
# -*- coding: utf-8 -*-
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# -------------------- Base (campos da tabela) --------------------
class EmpresaBase(BaseModel):
    # NOT NULL no banco
    nome: str = Field(..., min_length=1, description="Nome da empresa")
    # NOT NULL no banco
    descricao: str = Field(..., min_length=1, description="Descrição da empresa")
    # NULLABLE no banco
    ramo_de_atividade: Optional[str] = Field(
        None, description="Ramo/segmento (opcional)"
    )

    # Normaliza espaços
    @field_validator("nome", "descricao", "ramo_de_atividade")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            v = v.strip()
        return v or (None if v == "" else v)


# -------------------- Entrada (POST) --------------------
class EmpresaCreate(EmpresaBase):
    """Payload para criação de empresa."""
    pass


# -------------------- Entrada (PUT/PATCH) --------------------
class EmpresaUpdate(BaseModel):
    """Payload para atualização parcial/total da empresa."""
    nome: Optional[str] = Field(None, min_length=1)
    descricao: Optional[str] = Field(None, min_length=1)
    ramo_de_atividade: Optional[str] = None

    @field_validator("nome", "descricao", "ramo_de_atividade")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            v = v.strip()
        return v or (None if v == "" else v)


# -------------------- Saída (GET/POST/PUT response) --------------------
class EmpresaOut(EmpresaBase):
    id: int

    class Config:
        from_attributes = True  # Pydantic v2 (substitui orm_mode=True)
