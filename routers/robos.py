# routers/robos.py
from typing import List, Optional
import json

from fastapi import (
    APIRouter, Depends, HTTPException, status, Path, Response,
    UploadFile, File, Form, Body, Request
)
from sqlalchemy.orm import Session

from models.robos import Robo
from schemas.robos import RobosCreate, Robos as RoboSchema
from auth.dependencies import get_db, get_current_user
from models.users import User
from services.cache_service import cache_result, cache_service

router = APIRouter(prefix="/robos", tags=["Robos"])

# ---------------------------
# Helpers
# ---------------------------
def _to_schema(robo: Robo) -> RoboSchema:
    return RoboSchema(
        id=robo.id,
        nome=robo.nome,
        criado_em=robo.criado_em,
        performance=robo.performance,
        id_ativo=robo.id_ativo,
        tem_arquivo=bool(robo.arquivo_robo),
    )

def _clean_optional_int(raw: Optional[str]) -> Optional[int]:
    """Converte '', ' ', 'null', 'none' -> None; caso contrário tenta int()."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in ("", "null", "none"):
        return None
    try:
        return int(s)
    except ValueError:
        raise HTTPException(status_code=400, detail="id_ativo deve ser inteiro ou ausente.")

def _parse_performance_json(value: Optional[str]) -> Optional[List[str]]:
    """
    Aceita:
      - None/''                 -> None
      - JSON list ex.: '["10%","15%"]'
      - Texto simples ex.: 'fazer um teste' -> ["fazer um teste"]
    """
    if value is None:
        return None
    txt = value.strip()
    if txt == "":
        return None
    try:
        data = json.loads(txt)
        if isinstance(data, list) and all(isinstance(x, str) for x in data):
            return data
        if isinstance(data, str):
            return [data]
    except Exception:
        return [txt]
    raise HTTPException(status_code=400, detail='Formato inválido para "performance".')

# ---------- GET: Listar robôs (com cache) ----------
@router.get("/", response_model=List[RoboSchema], summary="Listar Robôs")
@cache_result(key_prefix="robos", ttl=600)
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
    summary="Criar Robô (multipart/form-data, arquivo opcional)",
)
async def criar_robo_multipart(
    nome: str = Form(..., description="Nome do robô"),
    id_ativo: Optional[str] = Form(None, description="ID do ativo (opcional)"),

    # >>> performance pode vir como lista (campos repetidos) OU como JSON string
    performance: Optional[List[str]] = Form(None, description="Repita a chave: performance=a&performance=b"),
    performance_json: Optional[str] = Form(None, description='Alternativa: JSON string ex. ["a","b"]'),

    # >>> apenas arquivo_robo
    arquivo_robo: Optional[UploadFile] = File(None, description="Arquivo do robô (opcional, salvo como bytea)"),

    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    id_ativo_int = _clean_optional_int(id_ativo)

    # normaliza performance
    perf_list: Optional[List[str]] = None
    if performance is not None:
        perf_list = [p for p in performance if isinstance(p, str) and p.strip() != ""]
        if not perf_list:
            perf_list = None
    elif performance_json is not None:
        perf_list = _parse_performance_json(performance_json)

    # arquivo
    content: Optional[bytes] = None
    if arquivo_robo is not None:
        content = await arquivo_robo.read()
        if content == b"":
            content = None

    novo = Robo(
        nome=nome,
        performance=perf_list,
        id_ativo=id_ativo_int,
        arquivo_robo=content,
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)

    cache_service.clear_pattern("robos:*")
    return _to_schema(novo)

# ---------- POST LEGADO: JSON (sem arquivo) ----------
@router.post(
    "/json",
    response_model=RoboSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Criar Robô (LEGADO) — JSON sem arquivo)",
)
def criar_robo_json(
    payload: RobosCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    novo = Robo(
        nome=payload.nome,
        performance=payload.performance,
        id_ativo=getattr(payload, "id_ativo", None),
        arquivo_robo=None,
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)

    cache_service.clear_pattern("robos:*")
    return _to_schema(novo)

# ---------- PUT: Atualizar robô (aceita JSON ou MULTIPART) ----------
@router.put("/{id}", response_model=RoboSchema, summary="Atualizar Robô")
async def atualizar_robo(
    request: Request,
    id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    robo = db.query(Robo).filter(Robo.id == id).first()
    if not robo:
        raise HTTPException(status_code=404, detail="Robô não encontrado")

    ctype = request.headers.get("content-type", "").lower()

    # -------- multipart (FormData) --------
    if "multipart/form-data" in ctype:
        form = await request.form()

        # nome
        if "nome" in form:
            nome = str(form.get("nome")).strip()
            if nome:
                robo.nome = nome

        # id_ativo
        if "id_ativo" in form:
            robo.id_ativo = _clean_optional_int(str(form.get("id_ativo")))

        # performance: valores repetidos + opção JSON
        perf_vals = form.getlist("performance")
        perf_json_val = form.get("performance_json")
        perf_list: Optional[List[str]] = None
        if perf_vals:
            perf_list = [str(x) for x in perf_vals if str(x).strip() != ""]
        elif perf_json_val is not None:
            perf_list = _parse_performance_json(str(perf_json_val))
        if perf_list is not None:
            robo.performance = perf_list

        # arquivo: somente "arquivo_robo"
        up = form.get("arquivo_robo")
        if isinstance(up, UploadFile):
            content = await up.read()
            robo.arquivo_robo = content if content != b"" else None

    # -------- JSON (legado) --------
    else:
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=422, detail="Corpo inválido")

        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="Corpo inválido")

        if "id_ativo" in payload and isinstance(payload["id_ativo"], str):
            s = payload["id_ativo"].strip().lower()
            payload["id_ativo"] = None if s in ("", "null", "none") else int(s)

        for field in ("nome", "performance", "id_ativo"):
            if field in payload:
                setattr(robo, field, payload[field])

    db.commit()
    db.refresh(robo)

    cache_service.clear_pattern("robos:*")
    return _to_schema(robo)

# ---------- DELETE ----------
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
