# routers/status_aplicacao.py
# -*- coding: utf-8 -*-
import os
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from database import engine

# Se quiser proteger o GET com login, descomente as 2 linhas abaixo
# from auth.dependencies import get_current_user
# from models.users import User

router = APIRouter(prefix="/status-aplicacao", tags=["Status da Aplicação"])

# Mesmo segredo configurado no servidor e no GitHub (Actions -> Secrets)
BACKEND_BOT_TOKEN = os.getenv("BACKEND_BOT_TOKEN")

# ---------- Schemas ----------
class PostStartIn(BaseModel):
    aplicacao_id: int  # usado no POST (início do deploy)

class PutUpdateIn(BaseModel):
    status: str = Field(..., regex="^(concluido|falhou|cancelado|em_andamento)$")
    resumo_do_erro: Optional[str] = None  # enviar quando status = falhou

class StatusOut(BaseModel):
    aplicacao_id: int
    status: str
    resumo_do_erro: Optional[str] = None

# ---------- Helpers ----------
def _require_bearer(auth_header: Optional[str]):
    if not BACKEND_BOT_TOKEN:
        raise HTTPException(500, "BACKEND_BOT_TOKEN não configurado")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token ausente")
    token = auth_header.split(" ", 1)[1].strip()
    if token != BACKEND_BOT_TOKEN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token inválido")

# ---------- APIs ----------
@router.post("", status_code=204)
def post_start(body: PostStartIn, authorization: Optional[str] = Header(None)):
    """
    Usado automaticamente no início do deploy -> status='em_andamento'
    """
    _require_bearer(authorization)
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO global.status_da_aplicacao (aplicacao_id, status, resumo_do_erro)
                VALUES (:aplicacao_id, 'em_andamento', NULL)
                ON CONFLICT (aplicacao_id) DO UPDATE
                  SET status = 'em_andamento',
                      resumo_do_erro = NULL;
            """),
            {"aplicacao_id": body.aplicacao_id}
        )
        conn.commit()
    return

@router.put("/{aplicacao_id}", status_code=204)
def put_update(aplicacao_id: int, body: PutUpdateIn, authorization: Optional[str] = Header(None)):
    """
    Usado pelo GitHub Actions ao finalizar (ou re-tentar) o deploy.
    status: 'concluido' | 'falhou' | 'cancelado' | 'em_andamento'
    resumo_do_erro: enviar SOMENTE quando 'falhou' (será ignorado nos demais)
    """
    _require_bearer(authorization)
    resumo = body.resumo_do_erro if body.status == "falhou" else None
    # (opcional) limitar tamanho para evitar registros gigantes
    if resumo and len(resumo) > 8000:
        resumo = resumo[-8000:]

    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO global.status_da_aplicacao (aplicacao_id, status, resumo_do_erro)
                VALUES (:aplicacao_id, :status, :resumo)
                ON CONFLICT (aplicacao_id) DO UPDATE
                  SET status = EXCLUDED.status,
                      resumo_do_erro = EXCLUDED.resumo_do_erro;
            """),
            {"aplicacao_id": aplicacao_id, "status": body.status, "resumo": resumo}
        )
        conn.commit()
    return

@router.get("/{aplicacao_id}", response_model=StatusOut)
def get_status(aplicacao_id: int):
    # Para exigir login: adicione parâmetro `current_user: User = Depends(get_current_user)`
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
