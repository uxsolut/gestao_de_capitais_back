# routers/status_aplicacao.py
# -*- coding: utf-8 -*-
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from database import engine
from auth.dependencies import get_current_user
from models.users import User

router = APIRouter(prefix="/status-aplicacao", tags=["Status da Aplicação"])

class PutUpdateIn(BaseModel):
    status: str = Field(..., regex="^(em_andamento|concluido|falhou|cancelado)$")
    resumo_do_erro: Optional[str] = None  # use quando status="falhou"

@router.put("/{aplicacao_id}", status_code=204)
def atualizar_status(
    aplicacao_id: int,
    body: PutUpdateIn,
    current_user: User = Depends(get_current_user),
):
    """
    Upsert do status da aplicação.
    - Se não existir, insere.
    - Se existir, atualiza.
    - Se status != 'falhou', limpa resumo_do_erro.
    """
    # valida existência da aplicação (UX melhor que deixar o FK estourar)
    with engine.connect() as conn:
        existe = conn.execute(
            text("SELECT 1 FROM global.aplicacoes WHERE id = :id LIMIT 1"),
            {"id": aplicacao_id},
        ).scalar()
    if not existe:
        raise HTTPException(status_code=404, detail="Aplicação não encontrada")

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
            {"id": aplicacao_id, "st": body.status, "rs": resumo},
        )
    # 204 No Content
