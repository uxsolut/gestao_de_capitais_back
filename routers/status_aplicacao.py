# routers/status_aplicacao.py
# -*- coding: utf-8 -*-
from typing import Optional, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

router = APIRouter(prefix="/status-aplicacao", tags=["Status da Aplicação"])


# Aceita apenas estes valores (compatível com Pydantic v1 e v2)
StatusLiteral = Literal["em_andamento", "concluido", "falhou", "cancelado"]


class PutUpdateIn(BaseModel):
    status: StatusLiteral
    resumo_do_erro: Optional[str] = None  # envie quando status="falhou"


def _require_bearer(auth_header: Optional[str]):
    # import atrasado evita falhas de env na carga do módulo
    import os
    token_cfg = os.getenv("BACKEND_BOT_TOKEN")
    if not token_cfg:
        # Só reclamamos aqui, quando a rota é chamada
        raise HTTPException(500, "BACKEND_BOT_TOKEN não configurado")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Bearer token ausente")
    if auth_header.split(" ", 1)[1].strip() != token_cfg:
        raise HTTPException(403, "Token inválido")


@router.put("/{aplicacao_id}", status_code=204)
def atualizar_status(
    aplicacao_id: int,
    body: PutUpdateIn,
    authorization: Optional[str] = Header(None),
):
    _require_bearer(authorization)

    # imports atrasados para evitar qualquer ciclo em import-time
    from database import engine

    # 1) valida existência da aplicação
    with engine.connect() as conn:
        existe = conn.execute(
            text("SELECT 1 FROM global.aplicacoes WHERE id = :id LIMIT 1"),
            {"id": aplicacao_id},
        ).scalar()

    if not existe:
        raise HTTPException(status_code=404, detail="Aplicação não encontrada")

    # 2) normaliza resumo
    resumo = body.resumo_do_erro if body.status == "falhou" else None
    if resumo and len(resumo) > 8000:  # ~200 linhas aprox
        resumo = resumo[-8000:]

    # 3) upsert no status
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO global.status_da_aplicacao (aplicacao_id, status, resumo_do_erro)
                VALUES (:id, :st, :rs)
                ON CONFLICT (aplicacao_id) DO UPDATE
                  SET status = EXCLUDED.status,
                      resumo_do_erro = EXCLUDED.resumo_do_erro
                """
            ),
            {"id": aplicacao_id, "st": body.status, "rs": resumo},
        )
    # 204 No Content
