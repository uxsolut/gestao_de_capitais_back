from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class OrdemCreate(BaseModel):
    comentario_ordem: str
    id_robo_user: Optional[int] = None
    id_user: Optional[int] = None
    numero_unico: Optional[str] = None
    quantidade: Optional[int] = None
    preco: Optional[float] = None
    conta_meta_trader: Optional[str] = None
    tipo: Optional[str] = None

class Ordem(BaseModel):
    id: int
    comentario_ordem: str
    id_robo_user: Optional[int] = None
    id_user: Optional[int] = None
    numero_unico: Optional[str] = None
    quantidade: Optional[int] = None
    preco: Optional[float] = None
    conta_meta_trader: Optional[str] = None
    tipo: Optional[str] = None
    criado_em: Optional[datetime] = None

    class Config:
        from_attributes = True