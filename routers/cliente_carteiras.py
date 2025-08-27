from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models.carteiras import Carteira
from schemas.cliente_carteiras import CarteiraCreate, CarteiraUpdate, CarteiraOut
from database import get_db
from auth.dependencies import get_current_user
from models.users import User

router = APIRouter(prefix="/carteiras", tags=["Carteiras"])

@router.get("/", response_model=list[CarteiraOut])
def listar_carteiras(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Carteira).filter(Carteira.id_user == user.id).all()

@router.post("/", response_model=CarteiraOut)
def criar_carteira(dados: CarteiraCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    nova = Carteira(nome=dados.nome, id_user=user.id)
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova

@router.put("/{id}", response_model=CarteiraOut)
def atualizar_carteira(id: int, dados: CarteiraUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    carteira = db.query(Carteira).filter(Carteira.id == id, Carteira.id_user == user.id).first()
    if not carteira:
        raise HTTPException(status_code=404, detail="Carteira não encontrada")

    carteira.nome = dados.nome
    db.commit()
    db.refresh(carteira)
    return carteira

# ✅ NOVO: DELETE /carteiras/{id}
@router.delete("/{id}", status_code=204)
def deletar_carteira(id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    carteira = db.query(Carteira).filter(Carteira.id == id, Carteira.id_user == user.id).first()
    if not carteira:
        raise HTTPException(status_code=404, detail="Carteira não encontrada")

    db.delete(carteira)
    db.commit()
    return None  # ou: return Response(status_code=204)
