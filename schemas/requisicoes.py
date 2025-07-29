from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

# ---------- SCHEMA DE CRIAÇÃO ----------
class RequisicaoCreate(BaseModel):
    tipo: str = Field(..., description="Tipo da requisição (buy, sell, etc.)")
    comentario_ordem: str = Field(..., max_length=1000, description="Comentário da ordem")
    quantidade: Optional[int] = Field(None, gt=0, description="Quantidade (deve ser positiva)")
    preco: Optional[Decimal] = Field(None, gt=0, description="Preço (deve ser positivo)")
    id_robo: Optional[int] = Field(None, description="ID do robô (pode ser nulo)")
    id_ativo: Optional[int] = Field(None, description="ID do ativo (pode ser nulo)")
    ids_contas: Optional[List[int]] = Field(None, description="IDs das contas vinculadas")

    @validator('tipo')
    def validar_tipo(cls, v):
        tipos_validos = ['buy', 'sell', 'buy_limit', 'sell_limit', 'buy_stop', 'sell_stop']
        if v.lower() not in tipos_validos:
            raise ValueError(f'Tipo deve ser um dos: {", ".join(tipos_validos)}')
        return v.lower()

# ---------- SCHEMA DE ATUALIZAÇÃO ----------
class RequisicaoUpdate(BaseModel):
    comentario_ordem: Optional[str] = Field(None, max_length=1000)
    quantidade: Optional[int] = Field(None, gt=0)
    preco: Optional[Decimal] = Field(None, gt=0)
    id_robo: Optional[int] = None
    id_ativo: Optional[int] = None
    ids_contas: Optional[List[int]] = None

# ---------- SCHEMA DE RETORNO ----------
class Requisicao(BaseModel):
    id: int
    tipo: str
    comentario_ordem: Optional[str] = None
    quantidade: Optional[int] = None
    preco: Optional[Decimal] = None
    id_robo: Optional[int] = None
    id_ativo: Optional[int] = None
    ids_contas: Optional[List[int]] = None
    criado_em: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None,
            datetime: lambda v: v.isoformat() if v else None
        }
