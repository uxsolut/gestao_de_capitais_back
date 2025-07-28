from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models.contas import Conta as ContaModel
from models.carteiras import Carteira as CarteiraModel
from schemas.contas import Conta, ContaCreate
from typing import List
from models.users import User
from auth.dependencies import get_current_user

router = APIRouter(prefix="/contas", tags=["Contas"])

# ---------- POST: Criar conta ----------
@router.post("/", response_model=Conta)
def criar_conta(
    conta: ContaCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    nova = ContaModel(**conta.dict())
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova

# ---------- GET: Listar todas ----------
@router.get("/", response_model=List[Conta])
def listar_contas(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(ContaModel).all()

# ---------- GET: Buscar contas por carteira ----------
@router.get("/carteira/{carteira_id}", response_model=List[Conta])
def get_contas_by_carteira_id(
    carteira_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    carteira = db.query(CarteiraModel).filter(CarteiraModel.id == carteira_id).first()
    if not carteira:
        raise HTTPException(status_code=404, detail="Carteira não encontrada")

    contas = db.query(ContaModel).filter(ContaModel.id_carteira == carteira_id).all()
    return contas

# ---------- DELETE: Deletar conta ----------
@router.delete("/{conta_id}")
def deletar_conta(
    conta_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conta = db.query(ContaModel).filter(ContaModel.id == conta_id).first()
    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    db.delete(conta)
    db.commit()
    return {"mensagem": "Conta deletada com sucesso"}
