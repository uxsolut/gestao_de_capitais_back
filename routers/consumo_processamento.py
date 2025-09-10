# routers/consumo_processamento.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
from typing import Optional, List, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from models.users import User
from auth.auth import verificar_senha

# ⚠️ manter estes imports para registrar mapeamentos
from models.aplicacao import Aplicacao  # noqa: F401
from models.requisicoes import Requisicao  # noqa: F401
from models.robos_do_user import RoboDoUser  # noqa: F401

from redis import asyncio as redis  # redis-py asyncio

# ======================================================================
# Config
# ======================================================================

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

TOKEN_HASH_PREFIX   = "tok:"                 # tok:<TOKEN_OPACO>  -> hash com {role, ...}
ACCOUNT_TOKEN_KEY   = "conta:{id}:token"     # string contendo o token opaco por conta
ACCOUNT_ORDERS_KEY  = "conta:{id}:orders"    # lista com ordens (strings JSON)

# !!! ajuste para o nome REAL no seu banco !!!
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
# Redis helper
# ======================================================================

def get_redis() -> redis.Redis:
    """
    Cria cliente Redis asyncio. from_url **não é awaitable**.
    """
    return redis.from_url(
        REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )

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
    key = f"{TOKEN_HASH_PREFIX}{token}"

    r = get_redis()
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
# Lua script: checa token da conta e drena a fila de ordens (atômico)
# ======================================================================

LUA_DRENO = """
-- KEYS[1] = conta:{id}:token
-- KEYS[2] = conta:{id}:orders
-- ARGV[1] = token da conta (vindo do Postgres)
local t = redis.call('GET', KEYS[1])
if not t then return { "__ERR__", "TOKEN_MISSING" } end
if t ~= ARGV[1] then return { "__ERR__", "TOKEN_INVALID" } end
local items = redis.call('LRANGE', KEYS[2], 0, -1)
redis.call('DEL', KEYS[2])
return items
"""

# ======================================================================
# Endpoint principal
# ======================================================================

@router.post("/consumir-ordem", response_model=ConsumirResp)
async def consumir_ordem(
    body: ConsumirReq,
    db: Session = Depends(get_db),
    _api_user = Depends(validate_api_user_bearer),
):
    # 1) Autentica usuário (email+senha)
    user: Optional[User] = db.query(User).filter(User.email == body.email).first()
    if not user or not verificar_senha(body.senha, user.senha):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    # 2) Confirma que a conta pertence ao usuário
    dono_conta = db.execute(
        text("SELECT id_user FROM contas WHERE id = :id"),
        {"id": body.id_conta},
    ).scalar()
    if dono_conta is None:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    if int(dono_conta) != int(user.id):
        raise HTTPException(status_code=403, detail="Conta não pertence ao usuário")

    # 3) Busca token da conta no Postgres
    token_row = db.execute(
        text(f"SELECT {ACCOUNT_TOKEN_COLUMN} FROM contas WHERE id = :id"),
        {"id": body.id_conta},
    ).first()
    if not token_row or not token_row[0]:
        raise HTTPException(status_code=400, detail="Conta sem token")
    token_conta_db: str = token_row[0]

    # 4) Redis: valida token da conta e drena ordens
    token_key  = ACCOUNT_TOKEN_KEY.format(id=body.id_conta)
    orders_key = ACCOUNT_ORDERS_KEY.format(id=body.id_conta)

    r = get_redis()
    try:
        res = await r.eval(LUA_DRENO, keys=[token_key, orders_key], args=[token_conta_db])
    finally:
        try:
            await r.aclose()
        except Exception:
            pass

    if isinstance(res, list) and len(res) == 2 and res[0] == "__ERR__":
        code = res[1]
        if code == "TOKEN_MISSING":
            raise HTTPException(status_code=401, detail="Token ausente/expirado no Redis")
        if code == "TOKEN_INVALID":
            raise HTTPException(status_code=401, detail="Token inválido para esta conta")
        raise HTTPException(status_code=400, detail=f"Erro: {code}")

    # 5) Parseia ordens e coleta ids/nums para atualizar status
    itens: List[str] = res or []
    ordens: List[Dict[str, Any]] = []
    ids: List[int] = []
    nums: List[str] = []

    for raw in itens:
        try:
            obj = json.loads(raw)
        except Exception:
            obj = {"raw": raw}
        ordens.append(obj)
        if isinstance(obj, dict):
            if isinstance(obj.get("id"), int):
                ids.append(obj["id"])
            if isinstance(obj.get("numero_unico"), str):
                nums.append(obj["numero_unico"])

    # 6) Atualiza status no Postgres (quando houver algo)
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
    if ids or nums:
        db.commit()

    return ConsumirResp(
        status="success",
        conta=body.id_conta,
        quantidade=len(ordens),
        ordens=ordens,
    )
