# -*- coding: utf-8 -*-
from enum import Enum
from typing import Optional
import re

from pydantic import BaseModel, EmailStr, field_validator, constr


class UserRole(str, Enum):
    admin = "admin"
    cliente = "cliente"


class UserBase(BaseModel):
    nome: str
    email: EmailStr
    cpf: Optional[str] = None
    # Agora tipado como Enum e com default coerente com o banco
    tipo_de_user: UserRole = UserRole.cliente

    # --- Validadores ---

    @field_validator("nome")
    @classmethod
    def validate_nome(cls, v: str) -> str:
        if not v or len(v.strip()) < 2:
            raise ValueError("Nome deve ter pelo menos 2 caracteres")
        return v.strip()

    @field_validator("cpf")
    @classmethod
    def validate_cpf(cls, v: Optional[str]) -> Optional[str]:
        if v:
            # Remove não dígitos
            cpf_numbers = re.sub(r"[^0-9]", "", v)
            if len(cpf_numbers) != 11:
                raise ValueError("CPF deve ter 11 dígitos")
            # Formata ###.###.###-##
            return f"{cpf_numbers[:3]}.{cpf_numbers[3:6]}.{cpf_numbers[6:9]}-{cpf_numbers[9:]}"
        return v


class UserCreate(UserBase):
    # Garante mínimo de 6 caracteres sem precisar de validador
    senha: constr(min_length=6)  # type: ignore[valid-type]

    # (Removido id_conta: não existe mais em users no seu modelo/DB.
    #  Se precisar manter por compatibilidade, adicione: `id_conta: Optional[int] = None`
    #  e configure FastAPI para ignorar campos extras.)

class User(UserBase):
    id: int

    class Config:
        from_attributes = True  # (equivalente ao antigo orm_mode=True no Pydantic v1)


class UserLogin(BaseModel):
    email: EmailStr
    senha: str
