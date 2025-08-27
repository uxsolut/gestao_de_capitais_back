# routers/consumo_processamento.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy import update, select, and_, desc, func
from passlib.context import CryptContext
import redis
import json
import structlog
import hmac
from typing import List, Dict, Any

# ===== Imports do projeto =====
from database import get_db
from models.users import User
from models.contas import Conta
from models.carteiras import Carteira
from models.ordens import Ordem, OrdemStatus   # Enum do status
from config import settings
# ==============================

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["Consumo Processamento"])

# Usa o mesmo scheme do resto para não duplicar no Swagger
bearer_scheme = HTTPBearer(scheme_name="BearerAuth")

# aceita bcrypt/pbkdf2/argon2
pwd_context = CryptContext(schemes=["bcrypt", "pbkdf2_sha256", "argon2"], deprecated="auto")


def _redis_global():
    # Tokens opacos (GLOBAL)
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
        db=int(getattr(settings, "REDIS_DB_GLOBAL", 0)),
        decode_responses=True,
    )


def _redis_ordens():
    # Payloads das ordens (DB separado)
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
        db=int(getattr(settings, "REDIS_DB_ORDENS", 1)),
        decode_responses=True,
    )


# ---------- Schemas ----------
class ConsumirContaRequest(BaseModel):
    email: EmailStr = Field(..., examples=["user@example.com"])
    senha: str = Field(..., examples=["string"])
    id_conta: int = Field(..., gt=0, examples=[123])

class ConsumirContaResponse(BaseModel):
    conta_id: int
    conta_meta_trader: str | None = None
    ordens_consumidas: List[int]
    payload: Dict[str, Any]

class ErrorResponse(BaseModel):
    detail: str


# ---------- Helpers ----------
def get_api_user_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente")
    return credentials.credentials


def verify_password(stored: str, plain: str) -> bool:
    """
    - Se 'stored' parece hash (bcrypt/pbkdf2/argon2), verifica com passlib.
    - Senão, compara texto em tempo constante (fallback).
    """
    if not isinstance(stored, str):
        return False
    s = stored.strip()
    p = (plain or "").strip()
    looks_hashed = (
        s.startswith("$2a$") or s.startswith("$2b$") or s.startswith("$2y$")
        or s.startswith("$argon2") or s.startswith("$pbkdf2-") or s.startswith("pbkdf2:")
    )
    if looks_hashed:
        try:
            return pwd_context.verify(p, s)
        except Exception:
            return False
    return hmac.compare_digest(s, p)


def _mask_token(tok: str) -> str:
    if not tok:
        return ""
    if len(tok) <= 8:
        return "***"
    return f"{tok[:4]}***{tok[-4:]}"


def _token_key_candidates(token: str) -> list[str]:
    """Gera chaves candidatas considerando namespaces do config e fallbacks."""
    ns_cfg = (getattr(settings, "OPAQUE_TOKEN_NAMESPACE", "") or "").strip() or "opaque"
    ns_sys = (getattr(settings, "SYSTEM_TOKEN_NAMESPACE", "") or "").strip()  # ex.: 'sys:tok'
    bases: list[str] = []
    for ns in [ns_cfg, "opaque", "tok", "usr:tok", ns_sys]:
        if ns and ns not in bases:
            bases.append(ns)
    return [f"{ns}:{token}" for ns in bases]


def _read_token_meta(r: redis.Redis, key: str) -> dict:
    """Lê metadados do token armazenados como HASH (HSET) ou STRING (SET)."""
    try:
        t = r.type(key)
    except Exception:
        return {}
    if t == "hash":
        return r.hgetall(key) or {}
    if t in ("string", "set", "none"):
        raw = r.get(key)
        if not raw:
            return {}
        # tenta JSON
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        # tenta k=v|k=v ou k=v;k=v ou só 'user_id'
        data = {}
        for part in raw.replace(";", "|").split("|"):
            part = part.strip()
            if not part:
                continue
            if "=" in part:
                k, v = part.split("=", 1)
                data[k.strip()] = v.strip()
            elif part.isdigit():
                data["user_id"] = part
        return data
    return {}


def validar_token_opaco_api_user(r: redis.Redis, token: str, expected_user_id: int) -> None:
    """
    Valida o token no Redis Global:
      - procura em múltiplos namespaces
      - aceita HASH (HSET) ou STRING (JSON / k=v|k=v)
      - exige role=api_user
      - Se meta.shared ∈ {1,true,yes} OU não houver user_id/uid -> NÃO checa user_id
      - Caso contrário, checa user_id == expected_user_id
    """
    keys = _token_key_candidates(token)
    meta = {}
    hit_key = None
    for k in keys:
        meta = _read_token_meta(r, k)
        if meta:
            hit_key = k
            break
    if not meta:
        logger.warning("Token não encontrado em nenhum namespace", token=_mask_token(token), tried=keys)
        raise HTTPException(status_code=401, detail="Token opaco inválido/expirado")

    role = (meta.get("role") or "").strip()
    if role != "api_user":
        logger.warning("Token com role incorreta", token=_mask_token(token), role=role, key=hit_key)
        raise HTTPException(status_code=403, detail="Token não possui role=api_user")

    # Detecta modo "shared"
    shared_raw = str(meta.get("shared", "")).strip().lower()
    is_shared = shared_raw in ("1", "true", "yes") or ("user_id" not in meta and "uid" not in meta)

    if not is_shared:
        uid_raw = (meta.get("user_id") or meta.get("uid") or "").strip()
        try:
            uid = int(uid_raw)
        except Exception:
            logger.warning("Token malformado (user_id inválido)", token=_mask_token(token), meta=meta, key=hit_key)
            raise HTTPException(status_code=401, detail="Token malformado")
        if uid != expected_user_id:
            logger.warning("Token pertence a outro usuário", token=_mask_token(token), uid=uid, expected=expected_user_id)
            raise HTTPException(status_code=403, detail="Token não pertence ao usuário")


# Fallback para Redis sem GETDEL
GETDEL_LUA = """
local v = redis.call('GET', KEYS[1])
if v then
  redis.call('DEL', KEYS[1])
end
return v
"""


# ---------- Endpoint ----------
@router.post(
    "/consumir-ordem",   # pode manter o mesmo path
    response_model=ConsumirContaResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Consome ordens por ID da conta",
    description="Autentica por email/senha + Bearer, verifica propriedade da conta, "
                "lê chave da conta em `contas.chave_do_token`, faz GETDEL no Redis e "
                "marca como CONSUMIDO as ordens presentes no payload.",
)
def consumir_ordem_por_conta(
    body: ConsumirContaRequest,
    request: Request,
    db: Session = Depends(get_db),
    bearer_token: str = Depends(get_api_user_token),
):
    log = logger.bind(endpoint="consumir-ordem", id_conta=body.id_conta, email=str(body.email))

    # 1) Usuário
    user: User | None = db.execute(
        select(User).where(func.lower(User.email) == func.lower(body.email))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    # 2) Senha
    if not verify_password(getattr(user, "senha", ""), body.senha):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    # 3) Token opaco role=api_user
    r_global = _redis_global()
    validar_token_opaco_api_user(r_global, bearer_token, user.id)

    # 4) Conta -> carteira -> usuário (garante posse)
    row = db.execute(
        select(Conta, Carteira)
        .join(Carteira, Conta.id_carteira == Carteira.id)
        .where(Conta.id == body.id_conta)
        .limit(1)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    conta, carteira = row

    if int(carteira.id_user) != int(user.id):
        raise HTTPException(status_code=403, detail="Conta não pertence ao usuário informado")

    # 5) Chave da conta
    key = getattr(conta, "chave_do_token", None)
    if not key:
        raise HTTPException(status_code=404, detail="Nenhum payload pendente para esta conta")

    # 6) PRIMEIRO consome do Redis; se falhar NÃO mexe no status
    r_ordens = _redis_ordens()
    try:
        try:
            raw = r_ordens.execute_command("GETDEL", key)
        except redis.ResponseError:
            raw = r_ordens.eval(GETDEL_LUA, 1, key)
    except Exception as e:
        log.error("Erro ao consumir Redis", error=str(e), key=key)
        raise HTTPException(status_code=500, detail="Falha ao ler dados no Redis")

    if raw is None:
        # nada para consumir -> mantém tudo como estava
        raise HTTPException(status_code=409, detail="Payload já consumido ou inexistente")

    # 7) Atualiza status das ordens envolvidas
    try:
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}

        ordens_ids: List[int] = []
        if isinstance(payload, dict) and isinstance(payload.get("ordens"), list):
            for o in payload["ordens"]:
                try:
                    ordens_ids.append(int(o.get("ordem_id")))
                except Exception:
                    pass
        elif isinstance(payload, dict) and "ordem_id" in payload:
            # legado
            try:
                ordens_ids.append(int(payload["ordem_id"]))
            except Exception:
                pass

        if ordens_ids:
            upd = db.execute(
                update(Ordem)
                .where(
                    and_(
                        Ordem.id.in_(ordens_ids),
                        Ordem.status == OrdemStatus.INICIALIZADO,
                        Ordem.conta_meta_trader == conta.conta_meta_trader,
                    )
                )
                .values(status=OrdemStatus.CONSUMIDO)
            )
            db.commit()
            log.info("Ordens marcadas como CONSUMIDO", count=upd.rowcount, ids=ordens_ids)
        else:
            # Não havia IDs; apenas devolvemos o payload bruto
            log.warning("Payload sem lista de ordens; nenhuma linha atualizada", key=key)

    except Exception as e:
        db.rollback()
        # (opcional) re-enfileirar o payload aqui também
        raise

    return ConsumirContaResponse(
        conta_id=conta.id,
        conta_meta_trader=getattr(conta, "conta_meta_trader", None),
        ordens_consumidas=ordens_ids,
        payload=payload if isinstance(payload, dict) else {"raw": raw},
    )
