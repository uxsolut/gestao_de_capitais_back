# schemas/analises.py
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

# entrada do POST (tudo opcional, exceto voto)
class AnaliseCreate(BaseModel):
    id_user: Optional[int] = Field(default=None, gt=0)
    telefone: Optional[str] = Field(default=None, min_length=3)
    voto: int = Field(..., ge=1, le=10)

class Analise(BaseModel):
    id: int
    id_user: Optional[int] = None
    telefone: Optional[str] = None
    voto: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
