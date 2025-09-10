# routers/consumo_processamento.py
# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any, Dict
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from models.users import User
from auth.auth import verificar_senha

import os
from redis import asyncio as redis  # cliente asyncio oficial
from redis.exceptions import AuthenticationError, ConnectionError
import json

# ===================== CONFIG =====================
# Use a URL completa vinda do ambiente (inclui usuário/senha se necessário).
# Ex.: REDIS_URL="redis://:SENHA@127.0.0.1:6379/0"  (usuário default habilitado)
# ou   REDIS_URL="redis://USUARIO:SENHA@127.0.0.1:6379/0" (ACL nomeada)
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

# Chaves/prefixos no Redis
TOKEN_HASH_PREFIX = "tok:"                  # tok:<TOKEN_OPACO>
ACCOUNT_TOKEN_KEY = "conta:{id}:token"      # string com token da conta
ACCOUNT_ORDERS_KEY = "conta:{id}:orders"    # list com ordens

# Nome EXATO da coluna na tabela `contas` que guarda o token
ACCOUNT_TOKEN_COLUMN = "chave_do_token"

# ===================== MODELOS =====================
class ConsumirReq(BaseModel):
    email: EmailStr
    senha: str
    id_conta: int

class ConsumirResp(BaseModel):
    status: str
    conta: int
    quantidade: int
    ordens: List[Dict[str, Any]]

# Agrupa no Swagger em "Processamento" e define o prefixo
router = APIRouter(prefix="/api/v1", tags=["Processamento"])

# ===================== REDIS HELPER =====================
def get_redis():
    """
    Cria um cliente Redis asyncio a partir da REDIS_URL.
    IMPORTANTE: from_url é síncrono (não usar await aqui).
    """
    return redis.from_url(
        REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )

# ===================== SEGURANÇA (HTTP Bearer) =====================
bearer_scheme = HTTPBearer(auto_error=False)

async def validate_api_user_bearer(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> Dict[str, Any]:
    """
    Valida Authorization: Bearer <token> usando o esquema de segurança do Swagger.
    O header não aparece como parâmetro e o Swagger exibe o botão "Authorize".
    Regra: o token precisa existir em tok:<token>, ter role=api_user e não estar expirado.
    """
    if credentials is None or not credentials.scheme or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = credentials.credentials.strip()
    key = f"{TOKEN_HASH_PREFIX}{token}"
    r = get_redis()
    try:
        try:
            data = await r.hgetall(key)
        except AuthenticationError:
            # Credencial do Redis inválida (senha/ACL) — tratar como 401
            raise HTTPException(status_code=401, detail="Redis auth failed")
        except ConnectionError:
            # Redis fora — serviço indisponível
            raise HTTPException(status_code=503, detail="Redis indisponível")

        if not data:
            raise HTTPException(status_code=401, detail="Invalid token")
        if data.get("role") != "api_user":
            raise HTTPException(status_code=403, detail="Insufficient role")

        ttl = await r.ttl(key)
        if ttl is not None and ttl <= 0:
            raise HTTPException(status_code=401, detail="Token expired")

        return {"token": token, "ttl": ttl, **data}
    finally:
        await r.close()

# ===================== LUA (DRENAGEM ATÔMICA) =====================
LUA_DRENO = """
-- KEYS[1]=conta:{id}:token ; KEYS[2]=conta:{id}:orders ; ARGV[1]=token_banco
local t = redis.call('GET', KEYS[1])
if not t then return { "__ERR__", "TOKEN_MISSING" } end
if t ~= ARGV[1] then return { "__ERR__", "TOKEN_INVALID" } end
local items = redis.call('LRANGE', KEYS[2], 0, -1)
redis.call('DEL', KEYS[2])
return items
"""

# ===================== ENDPOINT =====================
@router.post("/consumir-ordem", response_model=ConsumirResp)
async def consumir_ordem(
    body: ConsumirReq,
    db: Session = Depends(get_db),
    _api = Depends(validate_api_user_bearer),
):
    # 1) Autentica usuário por email/senha
    user: Optional[User] = db.query(User).filter(User.email == body.email).first()
    if not user or not verificar_senha(body.senha, user.senha):
        # 401 evita 500 e não vaza detalhes
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    # 2) (opcional) Checar vínculo conta→user se você tiver essa relação:
    # if not conta_pertence_ao_user(db, user.id, body.id_conta):
    #     raise HTTPException(status_code=403, detail="Sem acesso à conta")

    # 3) Ler token da conta no BANCO
    row = db.execute(
        text(f"SELECT {ACCOUNT_TOKEN_COLUMN} FROM contas WHERE id = :id"),
        {"id": body.id_conta}
    ).first()
    if not row or not row[0]:
        raise HTTPException(status_code=400, detail="Conta sem token")
    token_conta_db: str = row[0]

    # 4) Conferir com Redis e drenar ordens
    token_key  = ACCOUNT_TOKEN_KEY.format(id=body.id_conta)
    orders_key = ACCOUNT_ORDERS_KEY.format(id=body.id_conta)

    r = get_redis()
    try:
        try:
            res = await r.eval(LUA_DRENO, keys=[token_key, orders_key], args=[token_conta_db])
        except AuthenticationError:
            raise HTTPException(status_code=401, detail="Redis auth failed")
        except ConnectionError:
            raise HTTPException(status_code=503, detail="Redis indisponível")
    finally:
        await r.close()

    # 5) Interpreta retorno do Lua
    if isinstance(res, list) and len(res) == 2 and res[0] == "__ERR__":
        code = res[1]
        if code == "TOKEN_MISSING":
            raise HTTPException(status_code=401, detail="Token ausente/expirado no Redis")
        if code == "TOKEN_INVALID":
            raise HTTPException(status_code=401, detail="Token inválido para esta conta")
        raise HTTPException(status_code=400, detail=f"Erro: {code}")

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

    # 6) Atualizar status = 'Consumido' no banco (pelos IDs ou números únicos)
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
