# schemas/analises.py
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

# ---------- entrada do POST ----------
class AnaliseCreate(BaseModel):
    telefone: str = Field(..., min_length=3)       # tira espaços e valida tamanho no app se quiser
    voto: int = Field(..., ge=1, le=10)            # 1 a 10

# ---------- saída (response) ----------
class Analise(BaseModel):
    id: int
    id_user: int
    telefone: str
    voto: int
    created_at: datetime

    # pydantic v2: substitui "class Config: orm_mode = True"
    model_config = ConfigDict(from_attributes=True)
