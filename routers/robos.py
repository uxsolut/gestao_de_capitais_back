from fastapi import APIRouter, Form, Depends, Path, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from models.robos import Robo
from schemas.robos import RoboCreate, Robo as RoboSchema
from auth.dependencies import get_db, get_current_user
from models.users import User
from services.cache_service import cache_result, cache_service

router = APIRouter(prefix="/robos", tags=["Robos"])

# ---------- GET: Listar robôs (com cache) ----------
@router.get("/", response_model=List[RoboSchema])
@cache_result(key_prefix="robos", ttl=600)  # Cache por 10 minutos
def listar_robos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Robo).all()

# ---------- POST: Criar novo robô ----------
@router.post("/")
async def criar_robo(
    nome: str = Form(...),
    symbol: str = Form(...),
    performance: List[str] = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    novo_robo = Robo(
        nome=nome,
        symbol=symbol,
        performance=performance,
    )

    db.add(novo_robo)
    db.commit()
    db.refresh(novo_robo)
    
    # Limpar cache de robôs
    cache_service.clear_pattern("robos:*")

    return {"mensagem": "Robô criado com sucesso", "id": novo_robo.id}

# ---------- PUT: Atualizar robô existente ----------
@router.put("/{id}")
async def atualizar_robo(
    id: int = Path(...),
    nome: Optional[str] = Form(None),
    symbol: Optional[str] = Form(None),
    performance: Optional[List[str]] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    robo = db.query(Robo).filter(Robo.id == id).first()

    if not robo:
        raise HTTPException(status_code=404, detail="Robô não encontrado")

    if nome is not None:
        robo.nome = nome
    if symbol is not None:
        robo.symbol = symbol
    if performance is not None:
        robo.performance = performance

    db.commit()
    db.refresh(robo)
    
    # Limpar cache de robôs
    cache_service.clear_pattern("robos:*")

    return {"mensagem": "Robô atualizado com sucesso", "id": robo.id}

# ---------- DELETE: Remover robô ----------
@router.delete("/{id}", status_code=204)
def deletar_robo(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    robo = db.query(Robo).filter(Robo.id == id).first()

    if not robo:
        raise HTTPException(status_code=404, detail="Robô não encontrado")

    db.delete(robo)
    db.commit()
    
    # Limpar cache de robôs
    cache_service.clear_pattern("robos:*")

