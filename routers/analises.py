# routers/analises.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth.dependencies import get_db
from models.analises import Analise as AnaliseModel
from schemas.analises import AnaliseCreate, Analise as AnaliseSchema

router = APIRouter(prefix="/analises", tags=["Análises"])

@router.post(
    "/",
    response_model=AnaliseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Criar análise (público, sem login)",
    openapi_extra={"security": []},  # remove o cadeado no Swagger
)
def criar_analise(payload: AnaliseCreate, db: Session = Depends(get_db)):
    nova = AnaliseModel(
        id_user=payload.id_user,
        telefone=(payload.telefone.strip() if payload.telefone else None),
        voto=payload.voto,
        # created_at: deixa o server_default(now()) cuidar quando omitido
    )
    db.add(nova)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erro ao inserir análise: {e}")
    db.refresh(nova)
    return nova
