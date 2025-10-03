# routers/status_aplicacao.py
# -*- coding: utf-8 -*-
import os
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from database import engine

router = APIRouter(prefix="/status-aplicacao", tags=["Status da Aplicação"])

# --------- Schemas ---------
class PutUpdateIn(BaseModel):
    status: str = Field(..., regex="^(concluido|falhou|cancelado|em_andamento)$")
    resumo_do_erro: Optional[str] = None  # use quando status = falhou

class StatusOut(BaseModel):
    aplicacao_id: int
    status: str
    resumo_do_erro: Optional[str] = None

# --------- Helpers locais (sem ler env na importação) ---------
def _require_bearer(auth_header: Optional[str]):
    token_cfg = os.getenv("BACKEND_BOT_TOKEN")  # lido só na hora da requisição
    if not token_cfg:
        # Não derruba o servidor; apenas recusa a chamada protegida
        raise HTTPException(500, "BACKEND_BOT_TOKEN não configurado")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Bearer token ausente")
    if auth_header.split(" ", 1)[1].strip() != token_cfg:
        raise HTTPException(403, "Token inválido")

# --------- Endpoints ---------
@router.put("/{aplicacao_id}", status_code=204)
def put_update(aplicacao_id: int, body: PutUpdateIn, authorization: Optional[str] = Header(None)):
    _require_bearer(authorization)

    resumo = body.resumo_do_erro if body.status == "falhou" else None
    if resumo and len(resumo) > 8000:  # “200 linhas” aprox.
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

@router.get("/{aplicacao_id}", response_model=StatusOut)
def get_status(aplicacao_id: int):
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT aplicacao_id, status, resumo_do_erro
                  FROM global.status_da_aplicacao
                 WHERE aplicacao_id = :id
            """),
            {"id": aplicacao_id}
        ).mappings().first()
    if not row:
        raise HTTPException(404, "Status não encontrado para esta aplicação")
    return StatusOut(**row)
