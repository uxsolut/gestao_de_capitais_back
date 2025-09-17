# routers/analises.py
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from auth.dependencies import get_db, get_current_user  # já existentes no teu projeto
from models.users import User                           # seu modelo de usuário
from models.analises import Analise as AnaliseModel
from schemas.analises import AnaliseCreate, Analise as AnaliseSchema

router = APIRouter(prefix="/analises", tags=["Analises"])

@router.post("/", response_model=AnaliseSchema, status_code=status.HTTP_201_CREATED, summary="Criar análise")
def criar_analise(
    payload: AnaliseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # opcional: se quiser impedir votos repetidos por telefone no mesmo dia, coloque lógica aqui

    nova = AnaliseModel(
        id_user=current_user.id,
        telefone=payload.telefone,
        voto=payload.voto,
    )
    db.add(nova)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        # pode especializar erros (ex: FK) se quiser
        raise HTTPException(status_code=400, detail=f"Erro ao inserir análise: {e}")
    db.refresh(nova)
    return nova
