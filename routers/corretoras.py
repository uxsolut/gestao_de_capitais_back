from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models.corretoras import Corretora as CorretoraModel
from schemas.corretoras import Corretora, CorretoraCreate
from auth.dependencies import get_current_user
from models.users import User

router = APIRouter(prefix="/corretoras", tags=["Corretoras"])

# ---------- GET: Listar todas as corretoras ----------
@router.get("/", response_model=List[Corretora])
def listar_corretoras(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(CorretoraModel).all()

# ---------- POST: Criar nova corretora ---------
@router.post("/", response_model=Corretora)
def criar_corretora(
    corretora: CorretoraCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    nova = CorretoraModel(**corretora.dict())
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova

# ---------- PUT: Atualizar corretora ----------
@router.put("/{corretora_id}", response_model=Corretora)
def atualizar_corretora(
    corretora_id: int,
    corretora: CorretoraCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    obj = db.query(CorretoraModel).filter(CorretoraModel.id == corretora_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Corretora não encontrada")
    for field, value in corretora.dict().items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj

# ---------- DELETE: Remover corretora -----------
@router.delete("/{corretora_id}")
def deletar_corretora(
    corretora_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    obj = db.query(CorretoraModel).filter(CorretoraModel.id == corretora_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Corretora não encontrada")
    db.delete(obj)
    db.commit()
    return {"detail": "Corretora removida com sucesso"}
