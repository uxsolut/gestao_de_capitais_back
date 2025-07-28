from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

class RequisicaoCreate(BaseModel):
    tipo: str = Field(..., description="Tipo da requisição (buy, sell, etc.)")
    comentario_ordem: Optional[str] = Field(None, max_length=1000, description="Comentário da ordem")
    symbol: Optional[str] = Field(None, max_length=20, description="Símbolo do ativo")
    quantidade: Optional[int] = Field(None, gt=0, description="Quantidade (deve ser positiva)")
    preco: Optional[Decimal] = Field(None, gt=0, description="Preço (deve ser positivo)")
    id_robo: int = Field(..., description="ID do robô (obrigatório)")
    
    @validator('tipo')
    def validar_tipo(cls, v):
        tipos_validos = ['buy', 'sell', 'buy_limit', 'sell_limit', 'buy_stop', 'sell_stop']
        if v.lower() not in tipos_validos:
            raise ValueError(f'Tipo deve ser um dos: {", ".join(tipos_validos)}')
        return v.lower()
    
    @validator('symbol')
    def validar_symbol(cls, v):
        if v and len(v.strip()) == 0:
            raise ValueError('Symbol não pode ser vazio')
        return v.upper() if v else None

class RequisicaoUpdate(BaseModel):
    comentario_ordem: Optional[str] = Field(None, max_length=1000)
    symbol: Optional[str] = Field(None, max_length=20)
    quantidade: Optional[int] = Field(None, gt=0)
    preco: Optional[Decimal] = Field(None, gt=0)
    aprovado: Optional[bool] = None

class Requisicao(BaseModel):
    id: int
    tipo: str
    comentario_ordem: Optional[str] = None
    symbol: Optional[str] = None
    quantidade: Optional[int] = None
    preco: Optional[Decimal] = None
    aprovado: bool = Field(default=False, description="Status de aprovação")
    id_robo: Optional[int] = None
    ids_contas: Optional[List[int]] = Field(default=[], description="IDs das contas vinculadas")
    
    # ✅ Campos de auditoria
    criado_em: datetime
    atualizado_em: datetime
    criado_por: Optional[int] = None
    atualizado_por: Optional[int] = None

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: lambda v: float(v) if v else None,
            datetime: lambda v: v.isoformat() if v else None
        }

class RequisicaoDetalhada(Requisicao):
    """Schema com informações detalhadas incluindo relacionamentos"""
    robo_nome: Optional[str] = None
    criador_nome: Optional[str] = None
    atualizador_nome: Optional[str] = None
    contas_nomes: Optional[List[str]] = Field(default=[], description="Nomes das contas vinculadas")
    
    class Config:
        from_attributes = True

class RequisicaoCache(BaseModel):
    """Schema específico para dados em cache"""
    id: int
    tipo: str
    comentario_ordem: Optional[str] = None
    symbol: Optional[str] = None
    quantidade: Optional[float] = None
    preco: Optional[float] = None
    id_robo: int
    ids_contas: List[int]
    criado_em: str  # ISO format
    aprovado: bool
    cache_timestamp: Optional[str] = None  # Timestamp do cache
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

