# routers/tipo_de_ordem.py
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Path
from sqlalchemy.orm import Session

from auth.dependencies import get_db, get_current_user
from models.users import User
from models.tipo_de_ordem import TipoDeOrdem as TipoDeOrdemModel
from schemas.tipo_de_ordem import (
    TipoDeOrdem as TipoDeOrdemSchema,
    TipoDeOrdemCreate,
)

router = APIRouter(prefix="/tipo-de-ordem", tags=["Tipo de Ordem"])


# -------- GET: listar todos --------
@router.get("/", response_model=List[TipoDeOrdemSchema], summary="Listar tipos de ordem")
def listar_tipos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(TipoDeOrdemModel).order_by(TipoDeOrdemModel.id.desc()).all()


# -------- GET: por ID --------
@router.get(
    "/{tipo_id}",
    response_model=TipoDeOrdemSchema,
    summary="Obter um tipo de ordem pelo ID",
)
def obter_tipo(
    tipo_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = db.get(TipoDeOrdemModel, tipo_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Tipo de ordem não encontrado.")
    return obj


# -------- POST: criar --------
@router.post(
    "/",
    response_model=TipoDeOrdemSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Criar tipo de ordem",
)
def criar_tipo(
    item: TipoDeOrdemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Garante unicidade de nome_da_funcao
    if db.query(TipoDeOrdemModel).filter(
        TipoDeOrdemModel.nome_da_funcao == item.nome_da_funcao
    ).first():
        raise HTTPException(status_code=400, detail="nome_da_funcao já cadastrado.")

    obj = TipoDeOrdemModel(
        nome_da_funcao=item.nome_da_funcao.strip(),
        codigo_fonte=item.codigo_fonte,
        ids_robos=item.ids_robos or [],
        netting_ou_hedging=item.netting_ou_hedging.value,  # salva como string do ENUM
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
