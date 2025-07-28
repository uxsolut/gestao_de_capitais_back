from pydantic import BaseModel, EmailStr
from typing import Optional

class UserLogin(BaseModel):
    email: EmailStr
    senha: str

class UserLoginResponse(BaseModel):
    id: int
    nome: str
    email: EmailStr
    cpf: Optional[str] = None
    id_corretora: Optional[int] = None