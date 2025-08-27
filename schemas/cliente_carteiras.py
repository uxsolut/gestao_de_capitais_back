from pydantic import BaseModel
from typing import Optional

class CarteiraBase(BaseModel):
    nome: str

class CarteiraCreate(CarteiraBase):
    pass

class CarteiraUpdate(CarteiraBase):
    pass

class CarteiraOut(CarteiraBase):
    id: int

    class Config:
        orm_mode = True
