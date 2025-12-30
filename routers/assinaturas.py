# routers/assinaturas.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from models.contatos import Assinatura
from schemas.contatos import AssinaturaCreate, AssinaturaOut

router = APIRouter(prefix="/api/assinaturas", tags=["Assinaturas"])


@router.post("", response_model=AssinaturaOut)
def criar_assinatura(payload: AssinaturaCreate, db: Session = Depends(get_db)):
    # valida user existe em global.users
    row = db.execute(text("SELECT id FROM global.users WHERE id = :id"), {"id": payload.user_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User não encontrado")

    assinatura = Assinatura(nome=payload.nome, user_id=payload.user_id)
    db.add(assinatura)
    db.commit()
    db.refresh(assinatura)
    return assinatura


@router.get("", response_model=list[AssinaturaOut])
def listar_assinaturas(user_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Assinatura).order_by(Assinatura.id.desc())
    if user_id is not None:
        q = q.filter(Assinatura.user_id == user_id)
    return q.all()
