# routers/page_meta.py
# -*- coding: utf-8 -*-
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy import text
from sqlalchemy.engine import Result

from database import engine
from auth.dependencies import get_current_user
from models.users import User
from schemas.page_meta import PageMetaCreate, PageMetaOut

router = APIRouter(prefix="/aplicacoes", tags=["Page Meta"])

# -------- helpers ----------
def _app_exists(aplicacao_id: int) -> bool:
    with engine.begin() as conn:
        return bool(
            conn.execute(
                text("SELECT 1 FROM global.aplicacoes WHERE id = :id LIMIT 1"),
                {"id": aplicacao_id},
            ).scalar()
        )

def _row_to_out(row) -> PageMetaOut:
    return PageMetaOut(
        id=row["id"],
        aplicacao_id=row["aplicacao_id"],
        rota=row["rota"],
        lang_tag=row["lang_tag"],
        basic_meta=row["basic_meta"],
        social_og=row["social_og"],
        twitter_meta=row["twitter_meta"],
        jsonld_base=row["jsonld_base"],
        jsonld_product=row["jsonld_product"],
        jsonld_article=row["jsonld_article"],
        jsonld_localbiz=row["jsonld_localbiz"],
        alternates=row["alternates"],
        extras=row["extras"],
    )

# -------- POST (UPSERT) ----------
@router.post(
    "/{aplicacao_id}/page-meta",
    response_model=PageMetaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cria/atualiza SEO/metadata da página (chave: aplicacao_id + rota + lang_tag)",
)
def upsert_page_meta(
    aplicacao_id: int,
    body: PageMetaCreate = Body(...),
    current_user: User = Depends(get_current_user),
):
    if not _app_exists(aplicacao_id):
        raise HTTPException(status_code=404, detail="Aplicação não encontrada.")

    with engine.begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO metadados.page_meta (
                    aplicacao_id, rota, lang_tag,
                    basic_meta, social_og, twitter_meta,
                    jsonld_base, jsonld_product, jsonld_article, jsonld_localbiz,
                    alternates, extras
                )
                VALUES (
                    :aplicacao_id, :rota, :lang_tag,
                    CAST(:basic_meta AS jsonb), CAST(:social_og AS jsonb), CAST(:twitter_meta AS jsonb),
                    CAST(:jsonld_base AS jsonb), CAST(:jsonld_product AS jsonb), CAST(:jsonld_article AS jsonb), CAST(:jsonld_localbiz AS jsonb),
                    CAST(:alternates AS jsonb), CAST(:extras AS jsonb)
                )
                ON CONFLICT (aplicacao_id, rota, lang_tag) DO UPDATE SET
                    basic_meta      = EXCLUDED.basic_meta,
                    social_og       = EXCLUDED.social_og,
                    twitter_meta    = EXCLUDED.twitter_meta,
                    jsonld_base     = EXCLUDED.jsonld_base,
                    jsonld_product  = EXCLUDED.jsonld_product,
                    jsonld_article  = EXCLUDED.jsonld_article,
                    jsonld_localbiz = EXCLUDED.jsonld_localbiz,
                    alternates      = EXCLUDED.alternates,
                    extras          = EXCLUDED.extras,
                    updated_at      = now()
                RETURNING id, aplicacao_id, rota, lang_tag,
                          basic_meta, social_og, twitter_meta,
                          jsonld_base, jsonld_product, jsonld_article, jsonld_localbiz,
                          alternates, extras
            """),
            {
                "aplicacao_id": aplicacao_id,
                "rota": body.rota,
                "lang_tag": body.lang_tag,
                "basic_meta": body.basic_meta,
                "social_og": body.social_og,
                "twitter_meta": body.twitter_meta,
                "jsonld_base": body.jsonld_base,
                "jsonld_product": body.jsonld_product,
                "jsonld_article": body.jsonld_article,
                "jsonld_localbiz": body.jsonld_localbiz,
                "alternates": body.alternates,
                "extras": body.extras,
            },
        ).mappings().first()

    return _row_to_out(row)

# -------- GET: listar por aplicação ----------
@router.get(
    "/{aplicacao_id}/page-meta",
    response_model=List[PageMetaOut],
    summary="Lista todas as entradas de page_meta de uma aplicação",
)
def list_page_meta(
    aplicacao_id: int,
    current_user: User = Depends(get_current_user),
):
    if not _app_exists(aplicacao_id):
        raise HTTPException(status_code=404, detail="Aplicação não encontrada.")

    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT id, aplicacao_id, rota, lang_tag,
                       basic_meta, social_og, twitter_meta,
                       jsonld_base, jsonld_product, jsonld_article, jsonld_localbiz,
                       alternates, extras
                  FROM metadados.page_meta
                 WHERE aplicacao_id = :aplicacao_id
                 ORDER BY rota, lang_tag
            """),
            {"aplicacao_id": aplicacao_id},
        ).mappings().all()

    return [_row_to_out(r) for r in rows]

# -------- GET: pegar 1 por chave (rota + lang_tag) ----------
@router.get(
    "/{aplicacao_id}/page-meta/one",
    response_model=PageMetaOut,
    summary="Busca uma entrada por rota + lang_tag",
)
def get_one_page_meta(
    aplicacao_id: int,
    rota: str = Query("/", description="Ex.: '/', '/contato', '*'"),
    lang_tag: str = Query("pt-BR", description="Ex.: 'pt-BR', 'en-US'"),
    current_user: User = Depends(get_current_user),
):
    if not _app_exists(aplicacao_id):
        raise HTTPException(status_code=404, detail="Aplicação não encontrada.")

    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT id, aplicacao_id, rota, lang_tag,
                       basic_meta, social_og, twitter_meta,
                       jsonld_base, jsonld_product, jsonld_article, jsonld_localbiz,
                       alternates, extras
                  FROM metadados.page_meta
                 WHERE aplicacao_id = :aplicacao_id
                   AND rota = :rota
                   AND lang_tag = :lang_tag
                 LIMIT 1
            """),
            {"aplicacao_id": aplicacao_id, "rota": rota, "lang_tag": lang_tag},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Metadata não encontrada para essa rota/lang.")

    return _row_to_out(row)

# -------- DELETE: por chave ----------
@router.delete(
    "/{aplicacao_id}/page-meta",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove uma entrada por rota + lang_tag",
)
def delete_page_meta(
    aplicacao_id: int,
    rota: str = Query(...),
    lang_tag: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    if not _app_exists(aplicacao_id):
        raise HTTPException(status_code=404, detail="Aplicação não encontrada.")

    with engine.begin() as conn:
        res = conn.execute(
            text("""
                DELETE FROM metadados.page_meta
                 WHERE aplicacao_id = :aplicacao_id
                   AND rota = :rota
                   AND lang_tag = :lang_tag
            """),
            {"aplicacao_id": aplicacao_id, "rota": rota, "lang_tag": lang_tag},
        )
        if (res.rowcount or 0) == 0:
            raise HTTPException(status_code=404, detail="Nada para remover.")
    return None
