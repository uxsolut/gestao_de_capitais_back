# schemas/paginas_dinamicas.py
# -*- coding: utf-8 -*-
from typing import Optional, Literal
from pydantic import BaseModel, Field


# ----------------- Tipos (compatíveis com os ENUMs do Postgres) -----------------
DominioEnum = Literal["pinacle.com.br", "gestordecapitais.com", "tetramusic.com.br"]
FrontBackEnum = Literal["frontend", "backend", "fullstack"]
EstadoEnum = Literal["producao", "beta", "dev", "desativado"]


# ----------------- Base -----------------
class PaginaDinamicaBase(BaseModel):
    dominio: DominioEnum = Field(..., description="Valor do enum global.dominio_enum")
    slug: str = Field(
        ...,
        pattern=r"^[a-z0-9-]{1,64}$",
        description="Slug minúsculo com hífens (1 a 64 chars)",
    )
    url_completa: str
    front_ou_back: Optional[FrontBackEnum] = Field(
        None, description="Valor do enum gestor_capitais.frontbackenum"
    )
    estado: Optional[EstadoEnum] = Field(
        None, description="Valor do enum global.estado_enum"
    )


# ----------------- Create / Update -----------------
class PaginaDinamicaCreate(PaginaDinamicaBase):
    # bytes em Pydantic casa com BYTEA/LargeBinary no SQLAlchemy
    arquivo_zip: bytes


class PaginaDinamicaUpdate(BaseModel):
    dominio: Optional[DominioEnum] = Field(None, description="Valor do enum global.dominio_enum")
    slug: Optional[str] = Field(None, pattern=r"^[a-z0-9-]{1,64}$")
    url_completa: Optional[str] = None
    arquivo_zip: Optional[bytes] = None
    front_ou_back: Optional[FrontBackEnum] = Field(
        None, description="Valor do enum gestor_capitais.frontbackenum"
    )
    estado: Optional[EstadoEnum] = Field(
        None, description="Valor do enum global.estado_enum"
    )


# ----------------- Response -----------------
class PaginaDinamicaOut(PaginaDinamicaBase):
    id: int

    class Config:
        from_attributes = True  # (Pydantic v2) substitui orm_mode=True
