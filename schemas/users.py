from pydantic import BaseModel, EmailStr, validator
from typing import Optional
import re

class UserBase(BaseModel):
    nome: str
    email: EmailStr
    cpf: Optional[str] = None
    tipo_de_user: Optional[str] = "cliente"

class UserCreate(UserBase):
    senha: str
    id_conta: Optional[int] = None
    
    @validator('nome')
    def validate_nome(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('Nome deve ter pelo menos 2 caracteres')
        return v.strip()
    
    @validator('cpf')
    def validate_cpf(cls, v):
        if v:
            # Remove caracteres não numéricos
            cpf_numbers = re.sub(r'[^0-9]', '', v)
            if len(cpf_numbers) != 11:
                raise ValueError('CPF deve ter 11 dígitos')
            # Formatação padrão
            return f"{cpf_numbers[:3]}.{cpf_numbers[3:6]}.{cpf_numbers[6:9]}-{cpf_numbers[9:]}"
        return v
    
    @validator('senha')
    def validate_senha(cls, v):
        if len(v) < 6:
            raise ValueError('Senha deve ter pelo menos 6 caracteres')
        return v
    
    @validator('tipo_de_user')
    def validate_tipo_user(cls, v):
        if v not in ['admin', 'cliente']:
            raise ValueError('Tipo de usuário deve ser "admin" ou "cliente"')
        return v

class User(UserBase):
    id: int
    
    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    email: EmailStr
    senha: str

