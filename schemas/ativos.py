from pydantic import BaseModel

class AtivoResumo(BaseModel):
    id: int
    descricao: str

    class Config:
        orm_mode = True  # compatível com Pydantic v1/v2
