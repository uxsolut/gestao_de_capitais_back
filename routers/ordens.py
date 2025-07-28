from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from models.ordens import Ordem
from models.users import User
from schemas.ordens import OrdemCreate, Ordem as OrdemSchema
from auth.dependencies import get_db, get_current_user

router = APIRouter(prefix="/ordens", tags=["Ordem"])

# ---------- POST: Criar nova ordem ----------
@router.post("/", response_model=OrdemSchema)
def criar_ordem(
    item: OrdemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    nova_ordem = Ordem(**item.dict(exclude_unset=True))
    nova_ordem.id_user = current_user.id  # ✅ Garante que a ordem pertence ao usuário logado
    db.add(nova_ordem)
    db.commit()
    db.refresh(nova_ordem)
    return nova_ordem

# ---------- GET: Listar ordens do usuário ----------
@router.get("/", response_model=List[OrdemSchema])
def listar_ordens(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Ordem).filter(Ordem.id_user == current_user.id).all()

# ---------- GET: Listar ordens por ID do robô do usuário ----------
@router.get("/robo-user/{id_robo_user}", response_model=List[OrdemSchema])
def listar_ordens_por_robo_user(
    id_robo_user: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Ordem)
        .filter(Ordem.id_user == current_user.id)
        .filter(Ordem.id_robo_user == id_robo_user)
        .all()
    )
