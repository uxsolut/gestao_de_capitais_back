# -*- coding: utf-8 -*-
from typing import Optional
from pydantic import BaseModel, Field


# ----------------- Base -----------------
class PaginaDinamicaBase(BaseModel):
    dominio: str = Field(..., description="Valor do enum dominio_enum já existente no Postgres")
    slug: str = Field(
        ...,
        pattern=r"^[a-z0-9-]{1,64}$",
        description="Slug minúsculo com hífens (1 a 64 chars)",
    )
    url_completa: str


# ----------------- Create / Update -----------------
class PaginaDinamicaCreate(PaginaDinamicaBase):
    # bytes em Pydantic casa com BYTEA/LargeBinary no SQLAlchemy
    arquivo_zip: bytes


class PaginaDinamicaUpdate(BaseModel):
    dominio: Optional[str] = Field(None, description="Valor do enum dominio_enum")
    slug: Optional[str] = Field(None, pattern=r"^[a-z0-9-]{1,64}$")
    url_completa: Optional[str] = None
    arquivo_zip: Optional[bytes] = None


# ----------------- Response -----------------
class PaginaDinamicaOut(PaginaDinamicaBase):
    id: int

    class Config:
        from_attributes = True  # substitui orm_mode=True no Pydantic v2
