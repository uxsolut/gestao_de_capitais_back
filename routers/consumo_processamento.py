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

# ⚠️ IMPORTS SOMENTE PARA REGISTRAR OS MAPEAMENTOS (evitam InvalidRequestError)
from models.aplicacao import Aplicacao  # noqa: F401
from models.requisicoes import Requisicao  # noqa: F401
from models.robos_do_user import RoboDoUser  # noqa: F401

from redis import asyncio as redis  # cliente asyncio oficial do redis-py


# ======================================================================
# Config
# ======================================================================

# Use a variável de ambiente (é a que já está correta no processo 9102).
# Ex.: REDIS_URL=redis://:SENHA@127.0.0.1:6379/0
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

# Prefixos/keys no Redis
TOKEN_HASH_PREFIX   = "tok:"                 # tok:<TOKEN_OPACO>  -> hash com {role, ...}
ACCOUNT_TOKEN_KEY   = "conta:{id}:token"     # string contendo o token opaco por conta
ACCOUNT_ORDERS_KEY  = "conta:{id}:orders"    # lista com ordens (strings JSON)

# Nome EXATO da coluna no Postgres que guarda o token da conta
# ajuste para o nome real da sua tabela/coluna
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

async def get_redis() -> redis.Redis:
    """
    Abre uma conexão asyncio com o Redis usando REDIS_URL.
    """
    return await redis.from_url(
        REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )


# ======================================================================
# Segurança (HTTP Bearer) – integra com Swagger automaticamente
# ======================================================================

bearer_scheme = HTTPBearer(auto_error=False)

async def validate_api_user_bearer(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> Dict[str, Any]:
    """
    Valida Authorization: Bearer <token> olhando um hash no Redis:
      HGETALL tok:<token>  -> deve ter role=api_user e (opcionalmente) TTL > 0.

    Isso habilita o botão "Authorize" no Swagger para você informar o Bearer.
    """
    if credentials is None or not credentials.scheme or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = credentials.credentials.strip()
    key = f"{TOKEN_HASH_PREFIX}{token}"

    r = await get_redis()
    try:
        data = await r.hgetall(key)
        if not data:
            raise HTTPException(status_code=401, detail="Invalid token")

        if data.get("role") != "api_user":
            raise HTTPException(status_code=403, detail="Insufficient role")

        ttl = await r.ttl(key)
        # ttl pode vir -1 (sem expiração) ou -2 (não existe) dependendo da config,
        # mas como já checamos existência acima, tratamos somente <=0 como expirado.
        if ttl is not None and ttl <= 0:
            raise HTTPException(status_code=401, detail="Token expired")

        # Retorna info útil para logs se quiser
        return {"token": token, "ttl": ttl, **data}
    finally:
        await r.close()


# ======================================================================
# Lua script: confere o token da conta e drena a lista de ordens ATÔMICAMENTE
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
    _api_user = Depends(validate_api_user_bearer),  # força o Bearer válido
):
    """
    Fluxo:
      1) Autentica usuário (email+senha) para descobrir/confirmar o dono.
      2) Busca o token opaco da conta no Postgres.
      3) Confere o token da conta no Redis e drena as ordens de forma atômica (Lua).
      4) Atualiza status das ordens no Postgres para 'Consumido'.
      5) Retorna a lista de ordens consumidas.
    """

    # 1) Email/senha -> valida usuário
    user: Optional[User] = db.query(User).filter(User.email == body.email).first()
    if not user or not verificar_senha(body.senha, user.senha):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    # 2) Token de conta no Postgres
    row = db.execute(
        text(f"SELECT {ACCOUNT_TOKEN_COLUMN} FROM contas WHERE id = :id"),
        {"id": body.id_conta},
    ).first()

    if not row or not row[0]:
        raise HTTPException(status_code=400, detail="Conta sem token")

    token_conta_db: str = row[0]

    # 3) Redis: valida token e drena ordens
    token_key  = ACCOUNT_TOKEN_KEY.format(id=body.id_conta)
    orders_key = ACCOUNT_ORDERS_KEY.format(id=body.id_conta)

    r = await get_redis()
    try:
        res = await r.eval(LUA_DRENO, keys=[token_key, orders_key], args=[token_conta_db])
    finally:
        await r.close()

    # Tratamento de erros do Lua
    if isinstance(res, list) and len(res) == 2 and res[0] == "__ERR__":
        code = res[1]
        if code == "TOKEN_MISSING":
            raise HTTPException(status_code=401, detail="Token ausente/expirado no Redis")
        if code == "TOKEN_INVALID":
            raise HTTPException(status_code=401, detail="Token inválido para esta conta")
        raise HTTPException(status_code=400, detail=f"Erro: {code}")

    # 4) Parseia ordens e coleta ids/nums para atualizar status no banco
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

    # 5) Atualiza status no Postgres (quando houver algo para marcar)
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
