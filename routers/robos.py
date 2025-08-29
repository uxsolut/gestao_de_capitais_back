# routers/robos.py
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Path, Response
from sqlalchemy.orm import Session

from models.robos import Robo
from schemas.robos import RobosCreate, Robos as RoboSchema  # RoboSchema = saída
# Se você aplicou meu schema anterior, também existe RoboUpdate:
# from schemas.robos import RoboUpdate
from auth.dependencies import get_db, get_current_user
from models.users import User
from services.cache_service import cache_result, cache_service

router = APIRouter(prefix="/robos", tags=["Robos"])

# ---------- GET: Listar robôs (com cache) ----------
@router.get("/", response_model=List[RoboSchema], summary="Listar Robôs")
@cache_result(key_prefix="robos", ttl=600)  # Cache 10 min
def listar_robos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Robo).order_by(Robo.id).all()


# ---------- GET: Obter robô por ID ----------
@router.get("/{id}", response_model=RoboSchema, summary="Obter Robô")
def obter_robo(
    id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    robo = db.query(Robo).filter(Robo.id == id).first()
    if not robo:
        raise HTTPException(status_code=404, detail="Robô não encontrado")
    return robo


# ---------- POST: Criar novo robô (JSON) ----------
@router.post(
    "/",
    response_model=RoboSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Criar Robô",
)
def criar_robo(
    payload: RobosCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    novo_robo = Robo(
        nome=payload.nome,
        performance=payload.performance,
        # id_ativo existe no schema atualizado; se não tiver, remova a linha abaixo:
        id_ativo=getattr(payload, "id_ativo", None),
    )
    db.add(novo_robo)
    db.commit()
    db.refresh(novo_robo)

    # Limpa cache
    cache_service.clear_pattern("robos:*")

    return novo_robo


# ---------- PUT: Atualizar robô (JSON, parcial ou total) ----------
# Se você tiver o RoboUpdate no schemas, use-o aqui. Caso não tenha,
# mantenha Optional[RobosCreate] e trate com exclude_unset via .model_dump().
from fastapi import Body
def _apply_updates(robo: Robo, data: dict) -> None:
    # Campos permitidos
    for field in ("nome", "performance", "id_ativo"):
        if field in data:
            setattr(robo, field, data[field])

@router.put("/{id}", response_model=RoboSchema, summary="Atualizar Robô")
def atualizar_robo(
    id: int = Path(..., gt=0),
    payload: dict = Body(...),  # aceita JSON parcial; validação pode ser pelo schema RoboUpdate se preferir
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    robo = db.query(Robo).filter(Robo.id == id).first()
    if not robo:
        raise HTTPException(status_code=404, detail="Robô não encontrado")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Corpo inválido")

    _apply_updates(robo, payload)

    db.commit()
    db.refresh(robo)

    cache_service.clear_pattern("robos:*")
    return robo


# ---------- DELETE: Remover robô ----------
@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir Robô")
def deletar_robo(
    id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    robo = db.query(Robo).filter(Robo.id == id).first()
    if not robo:
        raise HTTPException(status_code=404, detail="Robô não encontrado")

    db.delete(robo)
    db.commit()

    cache_service.clear_pattern("robos:*")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
