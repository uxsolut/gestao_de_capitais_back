from typing import List, Optional
from pydantic import BaseModel, Field

# ---------- Já existentes ----------
class DashboardMetricas(BaseModel):
    total_carteiras: int
    total_robos: int
    total_ordens: int


class DashboardResumoDados(BaseModel):
    carteiras_recentes: List[str]
    ordens_recentes: List[str]


class DashboardResponse(BaseModel):
    metricas: DashboardMetricas
    resumo: DashboardResumoDados


# ---------- Gráfico de pizza (margem por país) ----------
class MargemPaisItem(BaseModel):
    pais: str                   # "Brasil", "Estados Unidos" ou "Outros"
    margem_total: float         # soma das margens das contas do usuário nesse país


class MargemPaisResponse(BaseModel):
    total: float                # soma geral (para cálculo de % no frontend)
    itens: List[MargemPaisItem] # sempre retornar nas 3 categorias


# ---------- Gráfico de evolução dos ativos ----------
class TipoMercadoOut(BaseModel):
    value: str = Field(..., description="Valor bruto do enum (ex.: 'Moeda', 'Indice', 'Robo')")
    label: str = Field(..., description="Rótulo para exibição")


class AtivoOut(BaseModel):
    id: int
    descricao: str
    symbol: str
    pais: Optional[str] = None

    # Pydantic v2: habilita from_attributes (ex-orm_mode)
    model_config = {"from_attributes": True}


class PontoSerie(BaseModel):
    data: str   # ISO date (YYYY-MM-DD)
    valor: float


class SerieAtivo(BaseModel):
    ativo_id: int
    symbol: str
    descricao: str
    pontos: List[PontoSerie]


class SeriesResponse(BaseModel):
    series: List[SerieAtivo]
