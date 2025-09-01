from typing import List, Optional
from pydantic import BaseModel


class ContaResponse(BaseModel):
    id: int
    nome: str
    conta_meta_trader: Optional[str]
    margem_total: Optional[float]
    margem_disponivel: Optional[float]
    # ↓ Ajustado para o POST aceitar sem corretora e não quebrar a resposta
    id_corretora: Optional[int]
    id_carteira: Optional[int]
    nome_corretora: Optional[str]

    class Config:
        orm_mode = True


class CorretoraResponse(BaseModel):
    id: int
    nome: str

    class Config:
        orm_mode = True


class RoboResponse(BaseModel):
    id: int
    nome: str
    performance: Optional[List[str]]

    class Config:
        orm_mode = True


class RoboDoUserResponse(BaseModel):
    id: int
    ligado: bool
    ativo: bool
    tem_requisicao: bool
    id_robo: int
    id_conta: Optional[int]
    id_carteira: Optional[int]
    nome_robo: str

    class Config:
        orm_mode = True


class ContaCreate(BaseModel):
    nome: str
    # ↓ Tornados opcionais para o POST /cliente/contas
    conta_meta_trader: Optional[str] = None
    id_corretora: Optional[int] = None
    id_carteira: int


class ContaUpdate(BaseModel):
    nome: str
    conta_meta_trader: str
    id_corretora: int


class RoboDoUserCreate(BaseModel):
    id_conta: int
    id_robo: int
    id_carteira: int
