# routers/consumo_processamento.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
from typing import Optional, List, Any, Dict, Tuple
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from models.users import User
from auth.auth import verificar_senha

# ⚠️ manter estes imports para registrar mapeamentos no processo 9102
from models.requisicoes import Requisicao  # noqa: F401
from models.robos_do_user import RoboDoUser  # noqa: F401
import models.tipo_de_ordem  # noqa: F401
import models.ordens  # noqa: F401
import models.robos  # noqa: F401
import models.users  # noqa: F401
import models.carteiras  # noqa: F401
import models.contas  # noqa: F401
import models.corretoras  # noqa: F401

from redis import asyncio as aioredis  # redis-py asyncio


# ======================================================================
# Config
# ======================================================================

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
OPAQUE_NS = (os.getenv("OPAQUE_TOKEN_NAMESPACE") or "tok").strip()

# nome REAL da coluna do token em public.contas
ACCOUNT_TOKEN_COLUMN = "chave_do_token"


# ======================================================================
# Schemas
# ======================================================================

class ConsumirReq(BaseModel):
    email: EmailStr
    senha: str
    id_conta: int


class ConsumirResp(BaseModel):
    status: str
    conta: int
    quantidade: int
    ordens: List[Dict[str, Any]]


# ======================================================================
# Router
# ======================================================================

router = APIRouter(prefix="/api/v1", tags=["Processamento"])


# ======================================================================
# Redis helpers
# ======================================================================

def _bump_db(url: str, db_index: int) -> str:
    p = urlparse(url)
    new_path = f"/{db_index}"
    return urlunparse((p.scheme, p.netloc, new_path, p.params, p.query, p.fragment))

def _redis_global() -> aioredis.Redis:
    """DB 0 – tokens opacos de 'api_user' (Bearer do Swagger)."""
    return aioredis.from_url(_bump_db(REDIS_URL, 0), encoding="utf-8", decode_responses=True)

def _redis_ordens() -> aioredis.Redis:
    """DB 1 – onde o writer grava as ordens por conta em tok:<token>."""
    return aioredis.from_url(_bump_db(REDIS_URL, 1), encoding="utf-8", decode_responses=True)

def _ensure_tok_prefix(k: str) -> str:
    if not k:
        return k
    return k if k.startswith(f"{OPAQUE_NS}:") else f"{OPAQUE_NS}:{k}"

# Lua para drenar de forma atômica: GET valor e DEL a chave (apaga o token do Redis).
# Retorna o valor antigo (ou nil).
REDIS_GETDEL_LUA = """
local k = KEYS[1]
local v = redis.call('GET', k)
if v then
  redis.call('DEL', k)
end
return v
"""


# ======================================================================
# Segurança (HTTP Bearer)
# ======================================================================

bearer_scheme = HTTPBearer(auto_error=False)

async def validate_api_user_bearer(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> Dict[str, Any]:
    if credentials is None or not credentials.scheme or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = credentials.credentials.strip()
    key = f"{OPAQUE_NS}:{token}"

    r = _redis_global()
    try:
        data = await r.hgetall(key)
        if not data:
            raise HTTPException(status_code=401, detail="Invalid token")

        if data.get("role") != "api_user":
            raise HTTPException(status_code=403, detail="Insufficient role")

        ttl = await r.ttl(key)
        if ttl is not None and ttl <= 0:
            raise HTTPException(status_code=401, detail="Token expired")

        return {"token": token, "ttl": ttl, **data}
    finally:
        try:
            await r.aclose()
        except Exception:
            pass


# ======================================================================
# Util: extrair ids de ordem para atualizar status
# ======================================================================

def _collect_ids_from_ordem(o: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    id_val = (
        o.get("id_ordem")
        or o.get("ordem_id")
        or o.get("order_id")
        or o.get("id")
    )
    try:
        oid = int(id_val) if id_val is not None else None
    except Exception:
        oid = None

    num = o.get("numero_unico")
    num = str(num) if isinstance(num, str) else None
    return oid, num


# ======================================================================
# Endpoint principal
# ======================================================================

@router.post("/consumir-ordem", response_model=ConsumirResp)
async def consumir_ordem(
    body: ConsumirReq,
    db: Session = Depends(get_db),
    _api_user = Depends(validate_api_user_bearer),  # força Bearer válido (role=api_user)
):
    # 🔒 0) Exclusão mútua por conta (evita corrida da MESMA conta)
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": int(body.id_conta)})

    # 1) Autentica usuário (email+senha)
    user: Optional[User] = db.query(User).filter(User.email == body.email).first()
    if not user or not verificar_senha(body.senha, user.senha):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    # 2) Confirma que a conta pertence ao usuário e lê a chave do token
    row = db.execute(
        text(f"""
            SELECT c.{ACCOUNT_TOKEN_COLUMN}
            FROM contas c
            JOIN carteiras ca ON ca.id = c.id_carteira
            WHERE c.id = :conta_id
              AND ca.id_user = :user_id
            LIMIT 1
        """),
        {"conta_id": body.id_conta, "user_id": user.id},
    ).first()

    if not row:
        raise HTTPException(status_code=403, detail="Conta não pertence ao usuário")

    chave_salva: Optional[str] = row[0]
    # ⚠️ A partir de agora, sem token passa a ser 401 (pedido seu)
    if not chave_salva:
        raise HTTPException(status_code=401, detail="Conta sem token")

    redis_key = _ensure_tok_prefix(chave_salva)

    # 3) Redis (DB=1): dreno atômico (GET + DEL) => também "apaga" o token no Redis
    r = _redis_ordens()
    try:
        try:
            payload_str = await r.eval(REDIS_GETDEL_LUA, 1, redis_key)
        except Exception:
            # Fallback para Redis sem EVAL (ou bloqueado): GETDEL (>= 6.2) ou GET+DEL
            try:
                payload_str = await r.getdel(redis_key)  # atomiza em versões novas
            except Exception:
                payload_str = await r.get(redis_key)
                if payload_str:
                    await r.delete(redis_key)

        if not payload_str:
            # também vamos zerar o token no banco se existir, para garantir 401 nas próximas
            db.execute(
                text(f"UPDATE contas SET {ACCOUNT_TOKEN_COLUMN} = NULL WHERE id = :conta_id"),
                {"conta_id": body.id_conta},
            )
            db.commit()
            raise HTTPException(status_code=401, detail="Token ausente/expirado no Redis")

        try:
            payload = json.loads(payload_str)
        except Exception:
            # zera token no banco mesmo assim
            db.execute(
                text(f"UPDATE contas SET {ACCOUNT_TOKEN_COLUMN} = NULL WHERE id = :conta_id"),
                {"conta_id": body.id_conta},
            )
            db.commit()
            raise HTTPException(status_code=400, detail="Payload inválido no Redis")

        ordens_list = payload.get("ordens") or []
        if not isinstance(ordens_list, list):
            ordens_list = []

        # 4) Se ficar vazio → 401 e token apagado (Redis já deletado; zera no banco)
        if len(ordens_list) == 0:
            db.execute(
                text(f"UPDATE contas SET {ACCOUNT_TOKEN_COLUMN} = NULL WHERE id = :conta_id"),
                {"conta_id": body.id_conta},
            )
            db.commit()
            raise HTTPException(status_code=401, detail="Sem ordens para consumir")

        # 5) Coleta ids para atualizar status (mantido igual ao seu)
        ids: List[int] = []
        nums: List[str] = []
        for o in ordens_list:
            if isinstance(o, dict):
                oid, num = _collect_ids_from_ordem(o)
                if oid is not None:
                    ids.append(oid)
                if num is not None:
                    nums.append(num)

        # 6) Marca como 'Consumido' no Postgres (igual ao seu arquivo)
        if ids:
            db.execute(
                text("UPDATE ordens SET status='Consumido'::ordem_status WHERE id = ANY(:ids)"),
                {"ids": ids},
            )
        if nums:
            db.execute(
                text("UPDATE ordens SET status='Consumido'::ordem_status WHERE numero_unico = ANY(:nums)"),
                {"nums": nums},
            )

        # 7) **Apaga o token no banco** (para o próximo pull já retornar 401)
        db.execute(
            text(f"UPDATE contas SET {ACCOUNT_TOKEN_COLUMN} = NULL WHERE id = :conta_id"),
            {"conta_id": body.id_conta},
        )

        # Commit das alterações (status + null no token)
        db.commit()

    finally:
        try:
            await r.aclose()
        except Exception:
            pass

    # 8) Resposta (primeiro consumo retorna as ordens e já invalida o token)
    return ConsumirResp(
        status="success",
        conta=body.id_conta,
        quantidade=len(ordens_list),
        ordens=ordens_list,
    )
