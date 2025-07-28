from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.projeto import Projeto as ProjetoModel
from schemas.projeto import Projeto, ProjetoCreate

router = APIRouter(prefix="/projetos", tags=["Projetos"])

# ---------- POST: Criar novo projeto ----------
@router.post("/", response_model=Projeto)
def criar_projeto(
    projeto: ProjetoCreate,
    db: Session = Depends(get_db),
):
    novo = ProjetoModel(**projeto.dict())
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo
