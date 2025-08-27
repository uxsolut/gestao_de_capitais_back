from typing import List, Optional
from pydantic import BaseModel


class ContaResponse(BaseModel):
    id: int
    nome: str
    conta_meta_trader: Optional[str]
    margem_total: Optional[float]
    margem_disponivel: Optional[float]
    id_corretora: int
    id_carteira: int
    nome_corretora: str

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
    conta_meta_trader: str
    id_corretora: int
    id_carteira: int


class ContaUpdate(BaseModel):
    nome: str
    conta_meta_trader: str
    id_corretora: int


class RoboDoUserCreate(BaseModel):
    id_conta: int
    id_robo: int
    id_carteira: int