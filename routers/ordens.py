# routers/ordens.py
from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from auth.dependencies import get_db, get_current_user
from models.ordens import Ordem
from models.users import User
from schemas.ordens import OrdemCreate, Ordem as OrdemSchema

router = APIRouter(prefix="/ordens", tags=["Ordem"])


# ---------- POST: Criar nova ordem ----------
@router.post(
    "/",
    response_model=OrdemSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Criar nova ordem"
)
def criar_ordem(
    item: OrdemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cria uma ordem. `status` e `criado_em` são definidos pelo banco (defaults).
    O `id_user` é sempre do usuário autenticado.
    """
    # Compatível com Pydantic v1 (.dict) e v2 (.model_dump)
    payload = item.model_dump(exclude_unset=True) if hasattr(item, "model_dump") else item.dict(exclude_unset=True)

    nova_ordem = Ordem(**payload)
    nova_ordem.id_user = current_user.id

    db.add(nova_ordem)
    db.commit()
    db.refresh(nova_ordem)
    return nova_ordem


# ---------- GET: Listar ordens do usuário ----------
@router.get(
    "/",
    response_model=List[OrdemSchema],
    summary="Listar ordens do usuário autenticado"
)
def listar_ordens(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retorna todas as ordens do usuário autenticado,
    ordenadas por `criado_em` (mais recentes primeiro).
    """
    return (
        db.query(Ordem)
        .filter(Ordem.id_user == current_user.id)
        .order_by(Ordem.criado_em.desc())
        .all()
    )
