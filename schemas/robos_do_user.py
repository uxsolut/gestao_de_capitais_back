from pydantic import BaseModel
from typing import Optional

class RoboDoUserCreate(BaseModel):
    id_robo: int
    ligado: Optional[bool] = False
    ativo: Optional[bool] = False
    tem_requisicao: Optional[bool] = False
    id_ordem: Optional[int] = None
    id_carteira: Optional[int] = None
    id_conta: Optional[int] = None

class RoboDoUser(BaseModel):
    id: int
    id_user: int
    id_robo: int
    ligado: Optional[bool] = False
    ativo: Optional[bool] = False
    tem_requisicao: Optional[bool] = False
    id_ordem: Optional[int] = None
    id_carteira: Optional[int] = None
    id_conta: Optional[int] = None

    class Config:
        from_attributes = True 