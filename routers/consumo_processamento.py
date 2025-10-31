# routers/consumo_processamento.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
import uuid
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

# lease/lock TTL em segundos (tempo máximo de processamento de um lote)
LOCK_TTL_SECONDS = int(os.getenv("CONSUMO_LOCK_TTL", "30"))


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
    return aioredis.from_url(
        _bump_db(REDIS_URL, 0),
        encoding="utf-8",
        decode_responses=True,
        socket_timeout=2.0,
        socket_connect_timeout=2.0,
    )

def _redis_ordens() -> aioredis.Redis:
    """DB 1 – onde o writer grava as ordens por conta em tok:<token>."""
    return aioredis.from_url(
        _bump_db(REDIS_URL, 1),
        encoding="utf-8",
        decode_responses=True,
        socket_timeout=2.0,
        socket_connect_timeout=2.0,
    )

def _ensure_tok_prefix(k: str) -> str:
    if not k:
        return k
    return k if k.startswith(f"{OPAQUE_NS}:") else f"{OPAQUE_NS}:{k}"


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
# Endpoint principal (lease + commit-first)
# ======================================================================

@router.post("/consumir-ordem", response_model=ConsumirResp)
async def consumir_ordem(
    body: ConsumirReq,
    db: Session = Depends(get_db),
    _api_user = Depends(validate_api_user_bearer),  # força Bearer válido (role=api_user)
):
    # 🔒 0) Exclusão mútua por conta no Postgres (serializa concorrência interna)
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
    if not chave_salva:
        # ⚠️ agora sem token é 401 (pedido seu)
        raise HTTPException(status_code=401, detail="Conta sem token")

    redis_key = _ensure_tok_prefix(chave_salva)
    lock_key = f"{redis_key}:lock"
    lock_val = str(uuid.uuid4())

    r = _redis_ordens()
    try:
        # 3) LEASE/LOCK no Redis: garante um consumidor por vez
        got_lock = await r.set(lock_key, lock_val, nx=True, ex=LOCK_TTL_SECONDS)
        if not got_lock:
            raise HTTPException(status_code=429, detail="Outro consumidor está processando este lote")

        try:
            # 4) Lê o payload SEM apagar (para não perder em caso de falha de commit)
            payload_str = await r.get(redis_key)
            if not payload_str:
                # zera token no banco para retornar 401 nos próximos pulls
                db.execute(
                    text(f"UPDATE contas SET {ACCOUNT_TOKEN_COLUMN} = NULL WHERE id = :conta_id"),
                    {"conta_id": body.id_conta},
                )
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                raise HTTPException(status_code=401, detail="Token ausente/expirado no Redis")

            try:
                payload = json.loads(payload_str)
            except Exception:
                db.execute(
                    text(f"UPDATE contas SET {ACCOUNT_TOKEN_COLUMN} = NULL WHERE id = :conta_id"),
                    {"conta_id": body.id_conta},
                )
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                raise HTTPException(status_code=400, detail="Payload inválido no Redis")

            ordens_list = payload.get("ordens") or []
            if not isinstance(ordens_list, list):
                ordens_list = []

            # 5) Se vazio → 401 e limpa token no banco (lock expira/libera)
            if len(ordens_list) == 0:
                db.execute(
                    text(f"UPDATE contas SET {ACCOUNT_TOKEN_COLUMN} = NULL WHERE id = :conta_id"),
                    {"conta_id": body.id_conta},
                )
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                raise HTTPException(status_code=401, detail="Sem ordens para consumir")

            # 6) Atualiza Postgres (idempotente do seu jeito) e COMMIT
            ids: List[int] = []
            nums: List[str] = []
            for o in ordens_list:
                if isinstance(o, dict):
                    oid, num = _collect_ids_from_ordem(o)
                    if oid is not None:
                        ids.append(oid)
                    if num is not None:
                        nums.append(num)

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

            # Commit das alterações de status
            try:
                db.commit()
            except Exception:
                db.rollback()
                # ⚠️ NÃO apaga o Redis: lote permanece para retry seguro
                raise

            # 7) Commit OK → apaga o lote no Redis e zera token no banco
            try:
                await r.delete(redis_key)
            finally:
                # mesmo que a deleção falhe, zeramos o token no banco
                db.execute(
                    text(f"UPDATE contas SET {ACCOUNT_TOKEN_COLUMN} = NULL WHERE id = :conta_id"),
                    {"conta_id": body.id_conta},
                )
                try:
                    db.commit()
                except Exception:
                    db.rollback()

        finally:
            # 8) Libera o lock somente se ainda for nosso (evita apagar lock de outro)
            try:
                cur = await r.get(lock_key)
                if cur == lock_val:
                    await r.delete(lock_key)
            except Exception:
                # se falhar, ele expira pelo TTL
                pass

    finally:
        try:
            await r.aclose()
        except Exception:
            pass

    # 9) Resposta (primeiro consumo retorna as ordens e já invalida o token)
    return ConsumirResp(
        status="success",
        conta=body.id_conta,
        quantidade=len(ordens_list),
        ordens=ordens_list,
    )
