# schemas/contatos.py
from datetime import datetime
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


class ExisteContatoResponse(BaseModel):
    exists: bool
    challenge_token: str | None = None
    expires_at: datetime | None = None


class ValidarCodigoResponse(BaseModel):
    ok: bool
    jwt: str | None = None
    token_type: str = "bearer"
    expires_minutes: int | None = None
