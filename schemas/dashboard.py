from pydantic import BaseModel
from typing import List

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
