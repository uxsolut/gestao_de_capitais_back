# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Optional, Annotated

from pydantic import BaseModel, Field

# Tipos anotados (em vez de constr/conint)
TelefoneStr = Annotated[str, Field(min_length=1, description="Telefone do contato")]
VotoInt = Annotated[int, Field(ge=1, le=10, description="Nota de 1 a 10")]


# ---------- Schemas ----------
class AnaliseBase(BaseModel):
    telefone: TelefoneStr
    voto: VotoInt


class AnaliseCreate(AnaliseBase):
    # id_user opcional (se ausente, rota usa current_user.id)
    id_user: Optional[int] = None


class AnaliseOut(BaseModel):
    id: int
    id_user: int
    telefone: str
    voto: int
    created_at: datetime

    # Compatível com Pydantic v1 e v2
    try:
        from pydantic import ConfigDict  # type: ignore
        model_config = ConfigDict(from_attributes=True)
    except Exception:  # Pydantic v1
        class Config:
            orm_mode = True
