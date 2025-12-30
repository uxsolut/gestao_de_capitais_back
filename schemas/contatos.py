# schemas/contatos.py
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class AssinaturaCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    user_id: int


class AssinaturaOut(BaseModel):
    id: int
    nome: str
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ContatoCreate(BaseModel):
    user_id: int
    nome: str = Field(min_length=2, max_length=160)
    telefone: str = Field(min_length=8, max_length=30)
    email: EmailStr
    assinatura_id: int


class ContatoOut(BaseModel):
    id: int
    user_id: int
    assinatura_id: int
    nome: str
    telefone: str
    email: EmailStr
    supervisor: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ===== Fluxo: "Existe contato" (Step 1) =====
class ExisteContatoRequest(BaseModel):
    email: EmailStr


class ExisteContatoResponse(BaseModel):
    exists: bool
    challenge_token: Optional[UUID] = None
    expires_at: Optional[datetime] = None


# ===== Fluxo: "Validar código" (Step 2) =====
class ValidarCodigoRequest(BaseModel):
    challenge_token: UUID
    code: str = Field(min_length=4, max_length=12)


class ValidarCodigoResponse(BaseModel):
    ok: bool
    jwt: Optional[str] = None
    token_type: str = "bearer"
    expires_minutes: Optional[int] = None
