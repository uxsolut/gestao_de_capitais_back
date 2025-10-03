# routers/status_aplicacao.py
# -*- coding: utf-8 -*-
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

router = APIRouter(prefix="/status-aplicacao", tags=["Status da Aplicação"])

class PutUpdateIn(BaseModel):
    status: str = Field(..., regex="^(em_andamento|concluido|falhou|cancelado)$")
    resumo_do_erro: Optional[str] = None  # envie quando status="falhou"

def _require_bearer(auth_header: Optional[str]):
    token_cfg = os.getenv("BACKEND_BOT_TOKEN")
    if not token_cfg:
        raise HTTPException(500, "BACKEND_BOT_TOKEN não configurado")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Bearer token ausente")
    if auth_header.split(" ", 1)[1].strip() != token_cfg:
        raise HTTPException(403, "Token inválido")

@router.put("/{aplicacao_id}", status_code=204)
def atualizar_status(aplicacao_id: int, body: PutUpdateIn, authorization: Optional[str] = Header(None)):
    """
    Upsert do status (1:1 por aplicacao_id).
    - Se não existir, insere.
    - Se existir, atualiza.
    - Se status != 'falhou', limpa resumo_do_erro.
    """
    _require_bearer(authorization)

    # import tardio evita ciclos em import-time
    from database import engine

    # valida existência da aplicação
    with engine.connect() as conn:
        existe = conn.execute(
            text("SELECT 1 FROM global.aplicacoes WHERE id = :id LIMIT 1"),
            {"id": aplicacao_id}
        ).scalar()
    if not existe:
        raise HTTPException(404, "Aplicação não encontrada")

    resumo = body.resumo_do_erro if body.status == "falhou" else None
    if resumo and len(resumo) > 8000:
        resumo = resumo[-8000:]

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO global.status_da_aplicacao (aplicacao_id, status, resumo_do_erro)
                VALUES (:id, :st, :rs)
                ON CONFLICT (aplicacao_id) DO UPDATE
                  SET status = EXCLUDED.status,
                      resumo_do_erro = EXCLUDED.resumo_do_erro;
            """),
            {"id": aplicacao_id, "st": body.status, "rs": resumo}
        )
    # 204 No Content
