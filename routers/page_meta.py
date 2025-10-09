# routers/page_meta.py
# -*- coding: utf-8 -*-
from typing import List, Optional
import os
import time
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, status, Body
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

# Reuso do que já existe no router de aplicações (mesma lógica do seu deploy)
from routers.aplicacoes import (
    _empresa_segment, _deploy_slug,
    BASE_UPLOADS_DIR, BASE_UPLOADS_URL, API_BASE_FOR_ACTIONS
)
from services.deploy_pages_service import GitHubPagesDeployer

router = APIRouter(prefix="/page-meta", tags=["Page Meta"])

# --------------------------------- helpers filhos ---------------------------------
def _is_empty_model(data) -> bool:
    # Considera "vazio" quando todos os campos são None
    return data is not None and all(getattr(data, f) is None for f in data.__fields__)

def _upsert_article(db: Session, page_meta_id: int, data: Optional[ArticleMeta]):
    if data is None:
        return
    if _is_empty_model(data):
        db.execute(text("DELETE FROM metadodos.page_meta_article WHERE page_meta_id = :id"), {"id": page_meta_id})
        return
    db.execute(text("""
        INSERT INTO metadados.page_meta_article
            (page_meta_id, type, headline, description, author_name, date_published, date_modified, cover_image_url)
        VALUES
            (:id, :type, :headline, :description, :author_name, :date_published, :date_modified, :cover_image_url)
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
        db.execute(text("DELETE FROM metadados.page_meta_product WHERE page_meta_id = :id"), {"id": page_meta_id})
        return
    db.execute(text("""
        INSERT INTO metadados.page_meta_product
            (page_meta_id, name, description, sku, brand, price_currency, price, availability, item_condition,
             price_valid_until, image_urls)
        VALUES
            (:id, :name, :description, :sku, :brand, :price_currency, :price, :availability, :item_condition,
             :price_valid_until, :image_urls)
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
        "price": str(data.price) if data.price is not None else None,
        "availability": data.availability,
        "item_condition": data.item_condition,
        "price_valid_until": data.price_valid_until,
        "image_urls": [str(u) for u in (data.image_urls or [])] or None,
    })

def _upsert_localbiz(db: Session, page_meta_id: int, data: Optional[LocalBusinessMeta]):
    if data is None:
        return
    if _is_empty_model(data):
        db.execute(text("DELETE FROM metadados.page_meta_localbusiness WHERE page_meta_id = :id"), {"id": page_meta_id})
        return
    db.execute(text("""
        INSERT INTO metadados.page_meta_localbusiness
            (page_meta_id, business_name, phone, price_range, street, city, region, zip,
             latitude, longitude, opening_hours, image_urls)
        VALUES
            (:id, :business_name, :phone, :price_range, :street, :city, :region, :zip,
             :latitude, :longitude, :opening_hours, :image_urls)
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
        "opening_hours": data.opening_hours,   # list -> jsonb
        "image_urls": [str(u) for u in (data.image_urls or [])] or None,
    })

# --------------------------- POST (JSON) + deploy ZIP ---------------------------
@router.post(
    "/", response_model=PageMetaOut, status_code=status.HTTP_201_CREATED,
    summary="Cria/atualiza Page Meta via JSON (mantém o contrato atual) e dispara deploy com ZIP salvo"
)
def create_or_update_page_meta_and_deploy(
    body: PageMetaCreate = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mantém o JSON cheião do Swagger, salva tudo e dispara o deploy reaproveitando o ZIP de global.aplicacoes."""
    # 1) UPSERT page_meta (pelo trio aplicacao_id+rota+lang_tag)
    exists = db.execute(
        select(PageMeta).where(
            PageMeta.aplicacao_id == body.aplicacao_id,
            PageMeta.rota == body.rota,
            PageMeta.lang_tag == body.lang_tag,
        )
    ).scalar_one_or_none()

    if exists:
        item = exists
        item.seo_title       = body.seo_title
        item.seo_description = body.seo_description
        item.canonical_url   = str(body.canonical_url)
        item.og_title        = body.og_title
        item.og_description  = body.og_description
        item.og_image_url    = str(body.og_image_url) if body.og_image_url else None
        item.og_type         = body.og_type or "website"
        item.site_name       = body.site_name
        db.add(item)
        db.commit()
        db.refresh(item)
    else:
        item = PageMeta(
            aplicacao_id=body.aplicacao_id,
            rota=body.rota,
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

    # 2) Filhos (opcionais)
    _upsert_article(db, item.id, body.article)
    _upsert_product(db, item.id, body.product)
    _upsert_localbiz(db, item.id, body.localbusiness)
    db.commit()
    db.refresh(item)

    # 3) Reaproveita o ZIP salvo em global.aplicacoes + status 'em andamento'
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

        # status 'em andamento'
        conn.execute(text("""
            INSERT INTO global.status_da_aplicacao (aplicacao_id, status, resumo_do_erro)
            VALUES (:id, 'em andamento', NULL)
            ON CONFLICT (aplicacao_id) DO UPDATE
              SET status='em andamento', resumo_do_erro=NULL
        """), {"id": body.aplicacao_id})

        empresa_seg = _empresa_segment(conn, id_empresa)

    estado_efetivo = estado or "producao"
    slug_deploy = _deploy_slug(slug, estado_efetivo)

    # 4) Dispara workflow de deploy (passando meta_rota/meta_lang/page_meta_id)
    try:
        if slug_deploy is not None:
            GitHubPagesDeployer().dispatch(
                domain=dominio,
                slug=slug_deploy or "",
                zip_url=zip_url,
                empresa=empresa_seg,
                id_empresa=id_empresa,
                aplicacao_id=body.aplicacao_id,
                api_base=API_BASE_FOR_ACTIONS,
                meta_rota=body.rota,
                meta_lang=body.lang_tag,
                page_meta_id=str(item.id),
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Metadados salvos, status atualizado, mas falhou o deploy: {e}")

    return item


# --------------------------- PUT (JSON) + deploy ZIP ---------------------------
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

    # Pode mudar a chave? então previne conflito
    if body.aplicacao_id or body.rota or body.lang_tag:
        new_ap = body.aplicacao_id or item.aplicacao_id
        new_ro = body.rota or item.rota
        new_la = body.lang_tag or item.lang_tag
        conflict = db.execute(
            select(PageMeta).where(
                PageMeta.id != page_meta_id,
                PageMeta.aplicacao_id == new_ap,
                PageMeta.rota == new_ro,
                PageMeta.lang_tag == new_la,
            )
        ).scalar_one_or_none()
        if conflict:
            raise HTTPException(status_code=409, detail="Conflito com (aplicacao_id, rota, lang_tag).")
        item.aplicacao_id, item.rota, item.lang_tag = new_ap, new_ro, new_la

    for field in ["seo_title","seo_description","og_title","og_description","og_type","site_name"]:
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

    # Reaproveita o mesmo fluxo de deploy (ZIP do banco + status)
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
            GitHubPagesDeployer().dispatch(
                domain=dominio,
                slug=slug_deploy or "",
                zip_url=zip_url,
                empresa=empresa_seg,
                id_empresa=id_empresa,
                aplicacao_id=item.aplicacao_id,
                api_base=API_BASE_FOR_ACTIONS,
                meta_rota=item.rota,
                meta_lang=item.lang_tag,
                page_meta_id=str(item.id),
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Metadados atualizados, mas falhou o deploy: {e}")

    return item


# --------------------------- GETs (inalterados) ---------------------------
@router.get("/", response_model=List[PageMetaOut])
def list_page_meta(
    aplicacao_id: Optional[int] = Query(default=None),
    rota: Optional[str] = Query(default=None),
    lang_tag: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(PageMeta)
    if aplicacao_id is not None:
        stmt = stmt.where(PageMeta.aplicacao_id == aplicacao_id)
    if rota:
        stmt = stmt.where(PageMeta.rota == rota)
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
