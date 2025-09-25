# schemas/aplicacoes.py
# -*- coding: utf-8 -*-
from typing import Optional, Literal
from pydantic import BaseModel, Field

# ----------------- Tipos (compatíveis com os ENUMs do Postgres) -----------------
DominioEnum = Literal["pinacle.com.br", "gestordecapitais.com", "tetramusic.com.br"]
FrontBackEnum = Literal["frontend", "backend", "fullstack"]
EstadoEnum = Literal["producao", "beta", "dev", "desativado"]

# ----------------- Base -----------------
class AplicacaoBase(BaseModel):
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
    id_empresa: Optional[int] = Field(
        None, description="FK opcional para global.empresas.id"
    )
    # Novas colunas booleanas (NOT NULL DEFAULT false no banco)
    precisa_logar: bool = Field(
        False, description="Se true, requer autenticação/JWT para acesso."
    )
    home: bool = Field(
        False, description="Marca a aplicação como homepage padrão do domínio."
    )

# ----------------- Create / Update -----------------
class AplicacaoCreate(AplicacaoBase):
    # bytes em Pydantic casa com BYTEA/LargeBinary no SQLAlchemy
    arquivo_zip: bytes

class AplicacaoUpdate(BaseModel):
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
    id_empresa: Optional[int] = Field(
        None, description="FK opcional para global.empresas.id"
    )
    precisa_logar: Optional[bool] = Field(
        None, description="Se informado, atualiza exigência de autenticação."
    )
    home: Optional[bool] = Field(
        None, description="Se informado, atualiza flag de homepage padrão."
    )

# ----------------- Response -----------------
class AplicacaoOut(AplicacaoBase):
    id: int

    class Config:
        from_attributes = True  # (Pydantic v2) substitui orm_mode=True
