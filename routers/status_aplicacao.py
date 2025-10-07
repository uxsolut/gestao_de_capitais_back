# routers/status_aplicacao.py
# -*- coding: utf-8 -*-
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import text

router = APIRouter(prefix="/status-aplicacao", tags=["Status da Aplicação"])

# ----------------------------- Helpers -----------------------------

_CANONICOS_DB = {
    "em andamento",
    "concluído",
    "falhou",
    "cancelado",
}

# aceita variações e mapeia p/ forma canônica do BANCO
_MAP_STATUS = {
    # em andamento
    "em_andamento": "em andamento",
    "em andamento": "em andamento",
    "em-andamento": "em andamento",
    "emandamento": "em andamento",

    # concluído
    "concluido": "concluído",   # sem acento -> com acento
    "concluído": "concluído",
    "concluido.": "concluído",  # casos com ruído
    "concluido ": "concluído",

    # falhou / cancelado (iguais)
    "falhou": "falhou",
    "cancelado": "cancelado",
}

def _normalize_status(raw: str) -> str:
    if raw is None:
        raise ValueError("status ausente")
    key = raw.strip().lower()
    # tira aspas acidentais
    if key.startswith('"') and key.endswith('"') and len(key) >= 2:
        key = key[1:-1].strip()
    norm = _MAP_STATUS.get(key)
    if not norm:
        raise ValueError(
            "Status inválido. Aceitos: "
            "'em_andamento'/'em andamento', 'concluido'/'concluído', 'falhou', 'cancelado'."
        )
    return norm

def _require_bearer(auth_header: Optional[str]):
    import os
    token_cfg = os.getenv("BACKEND_BOT_TOKEN")
    if not token_cfg:
        raise HTTPException(500, "BACKEND_BOT_TOKEN não configurado")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Bearer token ausente")
    if auth_header.split(" ", 1)[1].strip() != token_cfg:
        raise HTTPException(403, "Token inválido")

# ----------------------------- Schemas -----------------------------

class PutUpdateIn(BaseModel):
    # recebe qualquer string, valida e normaliza p/ forma do BANCO
    status: str
    resumo_do_erro: Optional[str] = None  # envie quando status == "falhou"

    @field_validator("status")
    @classmethod
    def _valida_status(cls, v: str) -> str:
        return _normalize_status(v)

# ------------------------------ Route ------------------------------

@router.put("/{aplicacao_id}", status_code=204)
def atualizar_status(
    aplicacao_id: int,
    body: PutUpdateIn,
    authorization: Optional[str] = Header(None),
):
    _require_bearer(authorization)

    from database import engine

    # 1) valida existência
    with engine.connect() as conn:
        existe = conn.execute(
            text("SELECT 1 FROM global.aplicacoes WHERE id = :id LIMIT 1"),
            {"id": aplicacao_id},
        ).scalar()
    if not existe:
        raise HTTPException(status_code=404, detail="Aplicação não encontrada")

    # 2) normaliza resumo (só guarda quando falhou)
    resumo = body.resumo_do_erro if body.status == "falhou" else None
    if resumo and len(resumo) > 8000:
        resumo = resumo[-8000:]

    # 3) upsert no status (gravando NA FORMA CANÔNICA DO BANCO)
    if body.status not in _CANONICOS_DB:
        # segurança extra (não deve acontecer por causa do validator)
        raise HTTPException(status_code=422, detail="Status não está na forma canônica")

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO global.status_da_aplicacao (aplicacao_id, status, resumo_do_erro)
                VALUES (:id, :st, :rs)
                ON CONFLICT (aplicacao_id) DO UPDATE
                  SET status = EXCLUDED.status,
                      resumo_do_erro = EXCLUDED.resumo_do_erro
            """),
            {"id": aplicacao_id, "st": body.status, "rs": resumo},
        )
    # 204 No Content
