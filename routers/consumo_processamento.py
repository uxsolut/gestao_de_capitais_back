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

# ⚠️ manter estes imports para registrar mapeamentos no processo 9102
from models.aplicacao import Aplicacao  # noqa: F401
from models.requisicoes import Requisicao  # noqa: F401
from models.robos_do_user import RoboDoUser  # noqa: F401
import models.projeto  # noqa: F401
import models.tipo_de_aplicacao  # noqa: F401
import models.versao_aplicacao  # noqa: F401
import models.tipo_de_ordem  # noqa: F401
import models.ordens  # noqa: F401
import models.robos  # noqa: F401
import models.users  # noqa: F401
import models.carteiras  # noqa: F401
import models.contas  # noqa: F401
import models.corretoras  # noqa: F401

from redis import asyncio as redis  # redis-py asyncio

# ======================================================================
# Config
# ======================================================================

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

TOKEN_HASH_PREFIX   = "tok:"                 # tok:<TOKEN_OPACO>  -> hash com {role, ttl, ...}
ACCOUNT_TOKEN_KEY   = "conta:{id}:token"     # string contendo o token opaco por conta
ACCOUNT_ORDERS_KEY  = "conta:{id}:orders"    # lista com ordens (strings JSON)

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
# Redis helper
# ======================================================================

def get_redis() -> redis.Redis:
    """Cria cliente Redis asyncio. from_url retorna o cliente (não precisa await)."""
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
            await r.close()
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

    # 2) Confirma que a conta pertence ao usuário via contas -> carteiras(id_user)
    #    e já traz o token da conta numa tacada só.
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

    token_conta_db: Optional[str] = row[0]
    if not token_conta_db:
        raise HTTPException(status_code=400, detail="Conta sem token")

    # 3) Redis: valida token da conta e drena ordens (EVAL correto no redis-py)
    token_key  = ACCOUNT_TOKEN_KEY.format(id=body.id_conta)
    orders_key = ACCOUNT_ORDERS_KEY.format(id=body.id_conta)

    r = get_redis()
    try:
        # assinatura: eval(script, numkeys, *keys_e_args)
        res = await r.eval(LUA_DRENO, 2, token_key, orders_key, token_conta_db)
    finally:
        try:
            await r.close()
        except Exception:
            pass

    if isinstance(res, list) and len(res) == 2 and res[0] == "__ERR__":
        code = res[1]
        if code == "TOKEN_MISSING":
            raise HTTPException(status_code=401, detail="Token ausente/expirado no Redis")
        if code == "TOKEN_INVALID":
            raise HTTPException(status_code=401, detail="Token inválido para esta conta")
        raise HTTPException(status_code=400, detail=f"Erro: {code}")

    # 4) Parseia ordens e coleta ids/nums para atualizar status
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
            _id = obj.get("id")
            if isinstance(_id, int):
                ids.append(_id)
            num = obj.get("numero_unico")
            if isinstance(num, str):
                nums.append(num)

    # 5) Atualiza status no Postgres (quando houver algo)
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

    # 6) Resposta
    return ConsumirResp(
        status="success",
        conta=body.id_conta,
        quantidade=len(ordens),
        ordens=ordens,
    )
