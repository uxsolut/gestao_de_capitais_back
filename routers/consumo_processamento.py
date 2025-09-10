# routers/consumo_processamento.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
from typing import Optional, List, Any, Dict, Tuple

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

from redis import asyncio as aioredis  # redis-py asyncio


# ======================================================================
# Config
# ======================================================================

# O processo já tem REDIS_URL com senha e /0.
# Global (tokens de API user) usa DB 0; ordens usam DB 1 (igual ao writer).
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

def _redis_global() -> aioredis.Redis:
    """DB 0 – tokens opacos de 'api_user' (Bearer do Swagger)."""
    return aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True, db=0)


def _redis_ordens() -> aioredis.Redis:
    """DB 1 – onde o writer grava as ordens por conta em tok:<token>."""
    return aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True, db=1)


def _ensure_tok_prefix(k: str) -> str:
    """Garante que a chave tenha o prefixo de namespace (ex.: 'tok:')."""
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
    """
    Suporta vários formatos vindos do writer:
      - id_ordem (preferido), ordem_id, order_id, id
      - numero_unico
    """
    id_val = (
        o.get("id_ordem") or
        o.get("ordem_id") or
        o.get("order_id") or
        o.get("id")
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
    # 1) Autentica usuário (email+senha)
    user: Optional[User] = db.query(User).filter(User.email == body.email).first()
    if not user or not verificar_senha(body.senha, user.senha):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    # 2) Confirma que a conta pertence ao usuário via contas -> carteiras(id_user)
    #    e já traz a chave do token (valor completo salvo pelo writer).
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
        raise HTTPException(status_code=400, detail="Conta sem token")

    # A coluna pode ter sido salva com ou sem prefixo; padroniza.
    redis_key = _ensure_tok_prefix(chave_salva)

    # 3) Redis (DB=1): lê o payload JSON da chave tok:<token>
    r = _redis_ordens()
    try:
        payload_str = await r.get(redis_key)
        if not payload_str:
            raise HTTPException(status_code=401, detail="Token ausente/expirado no Redis")

        try:
            payload = json.loads(payload_str)
        except Exception:
            raise HTTPException(status_code=400, detail="Payload inválido no Redis")

        ordens_list = payload.get("ordens") or []
        if not isinstance(ordens_list, list):
            ordens_list = []

        # 4) Coleta ids para atualizar status
        ids: List[int] = []
        nums: List[str] = []
        for o in ordens_list:
            if isinstance(o, dict):
                oid, num = _collect_ids_from_ordem(o)
                if oid is not None:
                    ids.append(oid)
                if num is not None:
                    nums.append(num)

        # 5) Marca como 'Consumido' no Postgres (quando houver algo)
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

        # 6) Drena: zera a lista e mantém o TTL atual
        ttl = await r.ttl(redis_key)
        payload["ordens"] = []
        if ttl is not None and ttl > 0:
            await r.set(redis_key, json.dumps(payload), ex=ttl)
        else:
            await r.set(redis_key, json.dumps(payload))  # sem expiração

    finally:
        try:
            await r.aclose()
        except Exception:
            pass

    # 7) Resposta
    return ConsumirResp(
        status="success",
        conta=body.id_conta,
        quantidade=len(ordens_list),
        ordens=ordens_list,
    )
