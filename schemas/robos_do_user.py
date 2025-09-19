# schemas/robos_do_user.py
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class RoboDoUserBase(BaseModel):
    id_robo: int = Field(..., description="FK para robos.id")
    id_carteira: Optional[int] = Field(None, description="FK opcional para carteiras.id")
    id_conta: Optional[int]   = Field(None, description="FK opcional para contas.id")
    id_ordem: Optional[int]   = Field(None, description="FK opcional para ordens.id")

    ligado: Optional[bool] = Field(False, description="Se o robô está ligado para essa conta")
    ativo: Optional[bool] = Field(False, description="Flag de ativo do vínculo")
    tem_requisicao: Optional[bool] = Field(False, description="Se há requisição pendente")

class RoboDoUserCreate(RoboDoUserBase):
    """Entrada para criação (id_user vem do JWT, não faz parte do body)."""
    pass

class RoboDoUserOut(RoboDoUserBase):
    """Resposta completa alinhada à tabela."""
    id: int
    id_user: int

    model_config = ConfigDict(from_attributes=True)
