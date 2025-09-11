# routers/robos.py
from typing import List, Optional
import json

from fastapi import (
    APIRouter, Depends, HTTPException, status, Path, Response,
    UploadFile, File, Form, Body
)
from sqlalchemy.orm import Session

from models.robos import Robo
from schemas.robos import RobosCreate, Robos as RoboSchema  # aliases compatíveis
from auth.dependencies import get_db, get_current_user
from models.users import User
from services.cache_service import cache_result, cache_service

router = APIRouter(prefix="/robos", tags=["Robos"])


# ---------------------------
# Helpers
# ---------------------------
def _to_schema(robo: Robo) -> RoboSchema:
    """Converte o ORM em schema incluindo tem_arquivo."""
    return RoboSchema(
        id=robo.id,
        nome=robo.nome,
        criado_em=robo.criado_em,
        performance=robo.performance,
        id_ativo=robo.id_ativo,
        tem_arquivo=bool(robo.arquivo_robo),
    )


def _parse_performance_field(value: Optional[str]) -> Optional[List[str]]:
    """
    Aceita performance como string JSON em multipart.
    - Se None/vazio -> retorna None.
    - Se inválido -> 400.
    """
    if value is None or value == "":
        return None
    try:
        data = json.loads(value)
        if not isinstance(data, list) or any(not isinstance(x, str) for x in data):
            raise ValueError
        return data
    except Exception:
        raise HTTPException(
            status_code=400,
            detail='Formato inválido para "performance". Envie JSON como ["10%","12%"].'
        )


# ---------- GET: Listar robôs (com cache) ----------
@router.get("/", response_model=List[RoboSchema], summary="Listar Robôs")
@cache_result(key_prefix="robos", ttl=600)  # Cache 10 min
def listar_robos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    itens = db.query(Robo).order_by(Robo.id).all()
    return [_to_schema(x) for x in itens]


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
    return _to_schema(robo)


# ---------- POST: Criar novo robô (MULTIPART) ----------
@router.post(
    "/",
    response_model=RoboSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Criar Robô (multipart/form-data, com arquivo opcional)",
)
async def criar_robo_multipart(
    nome: str = Form(..., description="Nome do robô"),
    id_ativo: Optional[int] = Form(None, description="ID do ativo (opcional)"),
    performance: Optional[str] = Form(
        None, description='Lista JSON (opcional), ex.: ["10%","15%"]'
    ),
    arquivo_robo: Optional[UploadFile] = File(
        None, description="Arquivo do robô (opcional, salvo como bytea)"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    perf_list = _parse_performance_field(performance)

    content: Optional[bytes] = None
    if arquivo_robo is not None:
        content = await arquivo_robo.read()
        if content == b"":
            content = None

    novo = Robo(
        nome=nome,
        performance=perf_list,   # pode ser None
        id_ativo=id_ativo,       # pode ser None
        arquivo_robo=content,    # pode ser None
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)

    cache_service.clear_pattern("robos:*")
    return _to_schema(novo)


# ---------- POST LEGADO: Criar robô (JSON puro, sem arquivo) ----------
@router.post(
    "/json",
    response_model=RoboSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Criar Robô (LEGADO) — JSON sem arquivo",
)
def criar_robo_json(
    payload: RobosCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    novo = Robo(
        nome=payload.nome,
        performance=payload.performance,  # pode ser None
        id_ativo=getattr(payload, "id_ativo", None),
        arquivo_robo=None,
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)

    cache_service.clear_pattern("robos:*")
    return _to_schema(novo)


# ---------- PUT: Atualizar robô (JSON, parcial ou total) ----------
def _apply_updates(robo: Robo, data: dict) -> None:
    for field in ("nome", "performance", "id_ativo"):
        if field in data:
            setattr(robo, field, data[field])

@router.put("/{id}", response_model=RoboSchema, summary="Atualizar Robô")
def atualizar_robo(
    id: int = Path(..., gt=0),
    payload: dict = Body(...),
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
    return _to_schema(robo)


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
