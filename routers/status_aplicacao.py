# routers/status_aplicacao.py
# -*- coding: utf-8 -*-
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from database import engine

router = APIRouter(prefix="/status-aplicacao", tags=["Status da Aplicação"])

# ---- body do PUT ----
class PutUpdateIn(BaseModel):
    status: str = Field(..., regex="^(em_andamento|concluido|falhou|cancelado)$")
    resumo_do_erro: Optional[str] = None  # use quando status="falhou"

# ---- auth simples por Bearer (token de integração) ----
def _require_bearer(auth_header: Optional[str]):
    token_cfg = os.getenv("BACKEND_BOT_TOKEN")
    if not token_cfg:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "BACKEND_BOT_TOKEN não configurado")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token ausente")
    if auth_header.split(" ", 1)[1].strip() != token_cfg:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token inválido")

@router.put("/{aplicacao_id}", status_code=status.HTTP_204_NO_CONTENT)
def atualizar_status(aplicacao_id: int, body: PutUpdateIn, authorization: Optional[str] = Header(None)):
    """
    Upsert do status da aplicação.
    - Se não existir, insere.
    - Se existir, atualiza.
    - Quando status != 'falhou', o resumo_do_erro é limpo (NULL).
    """
    _require_bearer(authorization)

    # valida se a aplicacao existe (melhor UX do que deixar o FK estourar)
    with engine.connect() as conn:
        existe = conn.execute(
            text("SELECT 1 FROM global.aplicacoes WHERE id = :id LIMIT 1"),
            {"id": aplicacao_id}
        ).scalar()

    if not existe:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aplicação não encontrada")

    resumo = body.resumo_do_erro if body.status == "falhou" else None
    if resumo and len(resumo) > 8000:  # ~200 linhas aprox.
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
