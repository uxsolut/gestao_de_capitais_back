from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models.ativos import Ativo
from schemas.ativos import AtivoResumo

router = APIRouter(prefix="/ativos", tags=["Ativos"])

@router.get("/", response_model=List[AtivoResumo])
def listar_ativos(db: Session = Depends(get_db)) -> List[AtivoResumo]:
    """
    Retorna apenas id e descricao dos ativos, em ordem de id.
    Ideal para dropdown no frontend.
    """
    rows = db.query(Ativo.id, Ativo.descricao).order_by(Ativo.id).all()
    return [AtivoResumo(id=r[0], descricao=r[1]) for r in rows]
