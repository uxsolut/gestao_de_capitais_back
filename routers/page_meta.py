# routers/page_meta.py
# -*- coding: utf-8 -*-
from typing import List, Optional
import os
import time
import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from sqlalchemy.orm import Session
from sqlalchemy import select, text
from database import get_db, engine

from auth.dependencies import get_current_user
from models.users import User
from models.page_meta import PageMeta
from schemas.page_meta import (
    PageMetaCreate, PageMetaUpdate, PageMetaOut,
    ArticleMeta, ProductMeta, LocalBusinessMeta
)
from routers.aplicacoes import (
    _empresa_segment, _deploy_slug,
    BASE_UPLOADS_DIR, BASE_UPLOADS_URL, API_BASE_FOR_ACTIONS
)
from services.deploy_pages_service import GitHubPagesDeployer

router = APIRouter(prefix="/page-meta", tags=["Page Meta"])


# ----------------------------- helpers -----------------------------
def _is_empty_model(data) -> bool:
    if data is None:
        return True
    try:
        payload = data.model_dump()
    except Exception:
        try:
            payload = data.dict()
        except Exception:
            return False
    for v in payload.values():
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        if isinstance(v, (list, dict)) and len(v) == 0:
            continue
        return False
    return True


def _ensure_leading_slash(path: str) -> str:
    if not path:
        return "/"
    path = path.strip()
    return path if path.startswith("/") else f"/{path}"


def _pg_text_array(values: Optional[List[str]]) -> Optional[str]:
    """Converte lista Python -> literal Postgres text[]: {"a","b"}"""
    if not values:
        return None
    def esc(s: str) -> str:
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return s
    return "{" + ",".join(f'"{esc(str(v))}"' for v in values) + "}"


def _upsert_article(db: Session, page_meta_id: int, data: Optional[ArticleMeta]):
    if data is None:
        return
    if _is_empty_model(data):
        db.execute(
            text("DELETE FROM metadados.page_meta_article WHERE page_meta_id = :id"),
            {"id": page_meta_id},
        )
        return
    db.execute(text("""
        INSERT INTO metadados.page_meta_article
            (page_meta_id, type, headline, description, author_name,
             date_published, date_modified, cover_image_url)
        VALUES
            (:id, :type, :headline, :description, :author_name,
             :date_published, :date_modified, :cover_image_url)
        ON CONFLICT (page_meta_id) DO UPDATE SET
            type = EXCLUDED.type,
            headline = EXCLUDED.headline,
            description = EXCLUDED.description,
            author_name = EXCLUDED.author_name,
            date_published = EXCLUDED.date_published,
            date_modified = EXCLUDED.date_modified,
            cover_image_url = EXCLUDED.cover_image_url,
            updated_at = now()
    """), {
        "id": page_meta_id,
        "type": data.type,
        "headline": data.headline,
        "description": data.description,
        "author_name": data.author_name,
        "date_published": data.date_published,
        "date_modified": data.date_modified,
        "cover_image_url": str(data.cover_image_url) if data.cover_image_url else None,
    })


def _upsert_product(db: Session, page_meta_id: int, data: Optional[ProductMeta]):
    if data is None:
        return
    if _is_empty_model(data):
        db.execute(
            text("DELETE FROM metadados.page_meta_product WHERE page_meta_id = :id"),
            {"id": page_meta_id},
        )
        return
    db.execute(text("""
        INSERT INTO metadados.page_meta_product
            (page_meta_id, name, description, sku, brand, price_currency, price,
             availability, item_condition, price_valid_until, image_urls)
        VALUES
            (:id, :name, :description, :sku, :brand, :price_currency, :price,
             :availability, :item_condition, CAST(:price_valid_until AS date), CAST(:image_urls AS text[]))
        ON CONFLICT (page_meta_id) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            sku = EXCLUDED.sku,
            brand = EXCLUDED.brand,
            price_currency = EXCLUDED.price_currency,
            price = EXCLUDED.price,
            availability = EXCLUDED.availability,
            item_condition = EXCLUDED.item_condition,
            price_valid_until = EXCLUDED.price_valid_until,
            image_urls = EXCLUDED.image_urls,
            updated_at = now()
    """), {
        "id": page_meta_id,
        "name": data.name,
        "description": data.description,
        "sku": data.sku,
        "brand": data.brand,
        "price_currency": data.price_currency,
        "price": data.price if isinstance(data.price, (Decimal, type(None))) else None,
        "availability": data.availability,
        "item_condition": data.item_condition,
        "price_valid_until": data.price_valid_until,
        "image_urls": _pg_text_array([str(u) for u in (data.image_urls or [])]) if data.image_urls else None,
    })


def _upsert_localbiz(db: Session, page_meta_id: int, data: Optional[LocalBusinessMeta]):
    if data is None:
        return
    if _is_empty_model(data):
        db.execute(
            text("DELETE FROM metadados.page_meta_localbusiness WHERE page_meta_id = :id"),
            {"id": page_meta_id},
        )
        return
    db.execute(text("""
        INSERT INTO metadados.page_meta_localbusiness
            (page_meta_id, business_name, phone, price_range, street, city, region, zip,
             latitude, longitude, opening_hours, image_urls)
        VALUES
            (:id, :business_name, :phone, :price_range, :street, :city, :region, :zip,
             :latitude, :longitude, :opening_hours::jsonb, CAST(:image_urls AS text[]))
        ON CONFLICT (page_meta_id) DO UPDATE SET
            business_name = EXCLUDED.business_name,
            phone = EXCLUDED.phone,
            price_range = EXCLUDED.price_range,
            street = EXCLUDED.street,
            city = EXCLUDED.city,
            region = EXCLUDED.region,
            zip = EXCLUDED.zip,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            opening_hours = EXCLUDED.opening_hours,
            image_urls = EXCLUDED.image_urls,
            updated_at = now()
    """), {
        "id": page_meta_id,
        "business_name": data.business_name,
        "phone": data.phone,
        "price_range": data.price_range,
        "street": data.street,
        "city": data.city,
        "region": data.region,
        "zip": data.zip,
        "latitude": data.latitude,
        "longitude": data.longitude,
        "opening_hours": json.dumps(list(data.opening_hours)) if data.opening_hours else json.dumps([]),
        "image_urls": _pg_text_array([str(u) for u in (data.image_urls or [])]) if data.image_urls else None,
    })


# --------------------------- POST (UPSERT + deploy) ---------------------------
@router.post(
    "/", response_model=PageMetaOut, status_code=status.HTTP_201_CREATED,
    summary="Cria/atualiza Page Meta e dispara deploy reaproveitando o ZIP salvo"
)
def create_or_update_page_meta_and_deploy(
    body: PageMetaCreate = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1) UPSERT page_meta pela chave composta
    row = db.execute(text("""
        SELECT id FROM metadados.page_meta
         WHERE aplicacao_id = :ap
           AND rota = :ro
           AND lang_tag = :la
         LIMIT 1
    """), {
        "ap": body.aplicacao_id,
        "ro": _ensure_leading_slash(body.rota),
        "la": body.lang_tag,
    }).mappings().first()

    if row:
        item = db.get(PageMeta, row["id"])
        item.seo_title = body.seo_title
        item.seo_description = body.seo_description
        item.canonical_url = str(body.canonical_url)
        item.og_title = body.og_title
        item.og_description = body.og_description
        item.og_image_url = str(body.og_image_url) if body.og_image_url else None
        item.og_type = body.og_type or "website"
        item.site_name = body.site_name
        db.add(item)
        db.commit()
        db.refresh(item)
    else:
        item = PageMeta(
            aplicacao_id=body.aplicacao_id,
            rota=_ensure_leading_slash(body.rota),
            lang_tag=body.lang_tag,
            seo_title=body.seo_title,
            seo_description=body.seo_description,
            canonical_url=str(body.canonical_url),
            og_title=body.og_title,
            og_description=body.og_description,
            og_image_url=str(body.og_image_url) if body.og_image_url else None,
            og_type=body.og_type or "website",
            site_name=body.site_name,
        )
        db.add(item)
        db.commit()
        db.refresh(item)

    # 2) Filhos opcionais
    _upsert_article(db, item.id, body.article)
    _upsert_product(db, item.id, body.product)
    _upsert_localbiz(db, item.id, body.localbusiness)
    db.commit()
    db.refresh(item)

    # 3) Preparação do ZIP + status
    if not BASE_UPLOADS_URL:
        raise HTTPException(status_code=500, detail="BASE_UPLOADS_URL não configurado.")
    os.makedirs(BASE_UPLOADS_DIR, exist_ok=True)

    with engine.begin() as conn:
        app_row = conn.execute(text("""
            SELECT id, dominio::text AS dominio, slug, estado::text AS estado, id_empresa, arquivo_zip
              FROM global.aplicacoes
             WHERE id = :id
             LIMIT 1
        """), {"id": body.aplicacao_id}).mappings().first()

        if not app_row:
            raise HTTPException(status_code=404, detail="Aplicação não encontrada para o aplicacao_id informado.")
        zip_bytes: bytes = app_row["arquivo_zip"]
        if not zip_bytes:
            raise HTTPException(status_code=400, detail="A aplicação não possui arquivo_zip salvo.")

        dominio    = app_row["dominio"]
        slug       = app_row["slug"]
        estado     = app_row["estado"]
        id_empresa = app_row["id_empresa"]

        ts = int(time.time())
        fname = f"{(slug or 'root')}-{body.aplicacao_id}-{ts}.zip"
        fpath = os.path.join(BASE_UPLOADS_DIR, fname)
        with open(fpath, "wb") as f:
            f.write(zip_bytes)
        zip_url = f"{BASE_UPLOADS_URL.rstrip('/')}/{fname}"

        conn.execute(text("""
            INSERT INTO global.status_da_aplicacao (aplicacao_id, status, resumo_do_erro)
            VALUES (:id, 'em andamento', NULL)
            ON CONFLICT (aplicacao_id) DO UPDATE
              SET status='em andamento', resumo_do_erro=NULL
        """), {"id": body.aplicacao_id})

        empresa_seg = _empresa_segment(conn, id_empresa)

    estado_efetivo = estado or "producao"
    slug_deploy = _deploy_slug(slug, estado_efetivo)

    try:
        if slug_deploy is not None:
            # apaga antes de publicar (idempotente)
            GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=slug_deploy or "")
            # publica
            GitHubPagesDeployer().dispatch(
                domain=dominio,
                slug=slug_deploy or "",
                zip_url=zip_url,
                empresa=empresa_seg or "",
                id_empresa=id_empresa,
                aplicacao_id=str(body.aplicacao_id),
                api_base=API_BASE_FOR_ACTIONS,
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Metadados salvos, status atualizado, mas falhou o deploy: {e}")

    return item


# --------------------------- PUT (update + deploy) ---------------------------
@router.put("/{page_meta_id}", response_model=PageMetaOut)
def update_page_meta_and_deploy(
    page_meta_id: int,
    body: PageMetaUpdate = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.get(PageMeta, page_meta_id)
    if not item:
        raise HTTPException(status_code=404, detail="page_meta não encontrada.")

    if body.aplicacao_id or body.rota or body.lang_tag:
        new_ap = body.aplicacao_id or item.aplicacao_id
        new_ro = _ensure_leading_slash(body.rota) if body.rota is not None else item.rota
        new_la = body.lang_tag or item.lang_tag

        # checa conflito
        row = db.execute(text("""
            SELECT id FROM metadados.page_meta
             WHERE id <> :cur
               AND aplicacao_id = :ap
               AND rota = :ro
               AND lang_tag = :la
             LIMIT 1
        """), {"cur": page_meta_id, "ap": new_ap, "ro": new_ro, "la": new_la}).mappings().first()
        if row:
            raise HTTPException(status_code=409, detail="Conflito com (aplicacao_id, rota, lang_tag).")

        item.aplicacao_id, item.rota, item.lang_tag = new_ap, new_ro, new_la

    for field in ["seo_title", "seo_description", "og_title", "og_description", "og_type", "site_name"]:
        val = getattr(body, field, None)
        if val is not None:
            setattr(item, field, val)

    if body.canonical_url is not None:
        item.canonical_url = str(body.canonical_url)
    if body.og_image_url is not None:
        item.og_image_url = str(body.og_image_url)

    db.add(item)
    db.commit()

    _upsert_article(db, item.id, body.article)
    _upsert_product(db, item.id, body.product)
    _upsert_localbiz(db, item.id, body.localbusiness)
    db.commit()
    db.refresh(item)

    if not BASE_UPLOADS_URL:
        raise HTTPException(status_code=500, detail="BASE_UPLOADS_URL não configurado.")
    os.makedirs(BASE_UPLOADS_DIR, exist_ok=True)

    with engine.begin() as conn:
        app_row = conn.execute(text("""
            SELECT id, dominio::text AS dominio, slug, estado::text AS estado, id_empresa, arquivo_zip
              FROM global.aplicacoes
             WHERE id = :id
             LIMIT 1
        """), {"id": item.aplicacao_id}).mappings().first()

        if not app_row:
            raise HTTPException(status_code=404, detail="Aplicação não encontrada para o aplicacao_id informado.")
        zip_bytes: bytes = app_row["arquivo_zip"]
        if not zip_bytes:
            raise HTTPException(status_code=400, detail="A aplicação não possui arquivo_zip salvo.")

        dominio    = app_row["dominio"]
        slug       = app_row["slug"]
        estado     = app_row["estado"]
        id_empresa = app_row["id_empresa"]

        ts = int(time.time())
        fname = f"{(slug or 'root')}-{item.aplicacao_id}-{ts}.zip"
        fpath = os.path.join(BASE_UPLOADS_DIR, fname)
        with open(fpath, "wb") as f:
            f.write(zip_bytes)
        zip_url = f"{BASE_UPLOADS_URL.rstrip('/')}/{fname}"

        conn.execute(text("""
            INSERT INTO global.status_da_aplicacao (aplicacao_id, status, resumo_do_erro)
            VALUES (:id, 'em andamento', NULL)
            ON CONFLICT (aplicacao_id) DO UPDATE
              SET status='em andamento', resumo_do_erro=NULL
        """), {"id": item.aplicacao_id})

        empresa_seg = _empresa_segment(conn, id_empresa)

    estado_efetivo = estado or "producao"
    slug_deploy = _deploy_slug(slug, estado_efetivo)

    try:
        if slug_deploy is not None:
            GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=slug_deploy or "")
            GitHubPagesDeployer().dispatch(
                domain=dominio,
                slug=slug_deploy or "",
                zip_url=zip_url,
                empresa=empresa_seg or "",
                id_empresa=id_empresa,
                aplicacao_id=str(item.aplicacao_id),
                api_base=API_BASE_FOR_ACTIONS,
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Metadados atualizados, mas falhou o deploy: {e}")

    return item


# --------------------------- GETs ---------------------------
@router.get(
    "/",
    response_model=List[PageMetaOut],
    summary="(PÚBLICO) Lista Page Meta filtrando por aplicação/rota/lang"
)
def list_page_meta(
    aplicacao_id: Optional[int] = Query(default=None),
    rota: Optional[str] = Query(default=None),
    lang_tag: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Endpoint público para o pipeline de deploy ler os metadados.
    Filtre sempre por aplicacao_id + rota + lang_tag para resultados precisos.
    """
    stmt = select(PageMeta)
    if aplicacao_id is not None:
        stmt = stmt.where(PageMeta.aplicacao_id == aplicacao_id)
    if rota:
        stmt = stmt.where(PageMeta.rota == _ensure_leading_slash(rota))
    if lang_tag:
        stmt = stmt.where(PageMeta.lang_tag == lang_tag)
    stmt = stmt.order_by(PageMeta.id.desc())
    return db.execute(stmt).scalars().all()


@router.get("/{page_meta_id}", response_model=PageMetaOut)
def get_page_meta(page_meta_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.get(PageMeta, page_meta_id)
    if not item:
        raise HTTPException(status_code=404, detail="page_meta não encontrada.")
    return item
