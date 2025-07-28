from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from auth.dependencies import get_current_user
from models.aplicacao import Aplicacao as AplicacaoModel
from models.versao_aplicacao import VersaoAplicacao
from schemas.aplicacao import Aplicacao, AplicacaoCreate
from models.users import User
from typing import Optional

router = APIRouter(prefix="/aplicacoes", tags=["Aplicacoes"])

# ---------- POST: Criar nova aplicação ----------
@router.post("/", response_model=Aplicacao)
def criar_aplicacao(
    aplicacao: AplicacaoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    nova = AplicacaoModel(**aplicacao.dict())
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova

# ---------- PUT: Atualizar campos ----------
@router.put("/{id}", response_model=Aplicacao)
def atualizar_aplicacao(
    id: int = Path(...),
    id_versao_aplicacao: Optional[int] = None,
    id_projeto: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = db.query(AplicacaoModel).filter(AplicacaoModel.id == id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Aplicação não encontrada")

    if id_versao_aplicacao is not None:
        app.id_versao_aplicacao = id_versao_aplicacao

    if id_projeto is not None:
        app.id_projeto = id_projeto

    total_versoes = db.query(func.count()).select_from(VersaoAplicacao).filter(
        VersaoAplicacao.id_aplicacao == app.id
    ).scalar()

    nome_base = app.nome.split(" - ")[0].strip()
    app.nome = f"{nome_base} - {total_versoes}"

    db.commit()
    db.refresh(app)
    return app
