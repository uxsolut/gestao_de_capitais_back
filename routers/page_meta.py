# routers/page_meta.py
# -*- coding: utf-8 -*-
from typing import List, Optional, Dict, Any
import os
import time
import json
from decimal import Decimal
from urllib.parse import urlsplit

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
from services.deploy_adapter import get_deployer

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


def _url_path_only(full: Optional[str]) -> str:
    """Extrai apenas o path da URL (sem domínio, sem query/fragment)."""
    if not full:
        return "/"
    try:
        parsed = urlsplit(full)
        path = parsed.path or "/"
        return _ensure_leading_slash(path)
    except Exception:
        # fallback simples
        if "://" in full:
            full = full.split("://", 1)[1]
            full = full[full.find("/") :] if "/" in full else ""
        return _ensure_leading_slash(full or "/")


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
            (page_meta_id, type, headline, description, author_name, image_urls)
        VALUES
            (:id, :type, :headline, :description, :author_name, CAST(:image_urls AS text[]))
        ON CONFLICT (page_meta_id) DO UPDATE SET
            type = EXCLUDED.type,
            headline = EXCLUDED.headline,
            description = EXCLUDED.description,
            author_name = EXCLUDED.author_name,
            image_urls = EXCLUDED.image_urls,
            updated_at = now()
    """), {
        "id": page_meta_id,
        "type": data.type,
        "headline": data.headline,
        "description": data.description,
        "author_name": data.author_name,
        "image_urls": _pg_text_array([str(u) for u in (getattr(data, "image_urls", []) or [])]) if getattr(data, "image_urls", None) else None,
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
             latitude, longitude, opening_hours, image_urls, logo_url)
        VALUES
            (:id, :business_name, :phone, :price_range, :street, :city, :region, :zip,
             :latitude, :longitude, CAST(:opening_hours AS jsonb), CAST(:image_urls AS text[]), :logo_url)
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
            logo_url = EXCLUDED.logo_url,
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
        "logo_url": str(getattr(data, "logo_url")) if getattr(data, "logo_url", None) else None,
    })


# ---------- helpers para montar a resposta com filhos ----------
def _fetch_children(db: Session, ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """
    Carrega filhos (article, product, localbusiness) para os page_meta_ids informados.
    Retorna: { page_meta_id: {"article": {...} | None, "product": {...}|None, "localbusiness": {...}|None } }
    """
    out: Dict[int, Dict[str, Any]] = {i: {"article": None, "product": None, "localbusiness": None} for i in ids}
    if not ids:
        return out

    # ARTICLE (sem datas)
    rows = db.execute(text("""
        SELECT page_meta_id, type, headline, description, author_name, image_urls
          FROM metadados.page_meta_article
         WHERE page_meta_id = ANY(:ids)
    """), {"ids": ids}).mappings().all()
    for r in rows:
        imgs = r["image_urls"]
        if isinstance(imgs, str):
            imgs = [s for s in imgs.strip("{}").split(",") if s != ""]
        out[r["page_meta_id"]]["article"] = {
            "type": r["type"],
            "headline": r["headline"],
            "description": r["description"],
            "author_name": r["author_name"],
            "image_urls": imgs,
        }

    # PRODUCT
    rows = db.execute(text("""
        SELECT page_meta_id, name, description, sku, brand, price_currency,
               price, availability, item_condition, price_valid_until, image_urls
          FROM metadados.page_meta_product
         WHERE page_meta_id = ANY(:ids)
    """), {"ids": ids}).mappings().all()
    for r in rows:
        imgs = r["image_urls"]
        if isinstance(imgs, str):
            imgs = [s for s in imgs.strip("{}").split(",") if s != ""]
        out[r["page_meta_id"]]["product"] = {
            "name": r["name"],
            "description": r["description"],
            "sku": r["sku"],
            "brand": r["brand"],
            "price_currency": r["price_currency"],
            "price": r["price"],
            "availability": r["availability"],
            "item_condition": r["item_condition"],
            "price_valid_until": r["price_valid_until"],
            "image_urls": imgs,
        }

    # LOCALBUSINESS
    rows = db.execute(text("""
        SELECT page_meta_id, business_name, phone, price_range, street, city, region, zip,
               latitude, longitude, opening_hours, image_urls, logo_url
          FROM metadados.page_meta_localbusiness
         WHERE page_meta_id = ANY(:ids)
    """), {"ids": ids}).mappings().all()
    for r in rows:
        imgs = r["image_urls"]
        if isinstance(imgs, str):
            imgs = [s for s in imgs.strip("{}").split(",") if s != ""]
        hours = r["opening_hours"]
        if isinstance(hours, str):
            try:
                hours = json.loads(hours)
            except Exception:
                hours = []
        out[r["page_meta_id"]]["localbusiness"] = {
            "business_name": r["business_name"],
            "phone": r["phone"],
            "price_range": r["price_range"],
            "street": r["street"],
            "city": r["city"],
            "region": r["region"],
            "zip": r["zip"],
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "opening_hours": hours or [],
            "image_urls": imgs,
            "logo_url": r["logo_url"],
        }

    return out


def _to_out_dict(pm: PageMeta, children: Dict[str, Any]) -> Dict[str, Any]:
    """Monta um dict compatível com PageMetaOut (com filhos)."""
    return {
        "id": pm.id,
        "aplicacao_id": pm.aplicacao_id,
        "rota": pm.rota,
        "lang_tag": pm.lang_tag,
        "seo_title": pm.seo_title,
        "seo_description": pm.seo_description,
        "canonical_url": pm.canonical_url,
        "og_title": pm.og_title,
        "og_description": pm.og_description,
        "og_image_url": pm.og_image_url,
        "og_type": pm.og_type,
        "site_name": pm.site_name,
        "article": children.get("article"),
        "product": children.get("product"),
        "localbusiness": children.get("localbusiness"),
    }


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
    # 0) Busca dados da aplicação (para canonical e rota)
    with engine.begin() as conn:
        app_row = conn.execute(text("""
            SELECT
                id,
                dominio::text AS dominio,
                slug,
                estado::text AS estado,
                id_empresa,
                arquivo_zip,
                url_completa::text AS url_completa
            FROM global.aplicacoes
            WHERE id = :id
            LIMIT 1
        """), {"id": body.aplicacao_id}).mappings().first()

        if not app_row:
            raise HTTPException(status_code=404, detail="Aplicação não encontrada para o aplicacao_id informado.")

    canonical_from_app = app_row["url_completa"]
    rota_from_app = _url_path_only(canonical_from_app)

    # 1) UPSERT page_meta pela chave composta (rota derivada)
    derived_rota = rota_from_app
    row = db.execute(text("""
        SELECT id FROM metadados.page_meta
         WHERE aplicacao_id = :ap
           AND rota = :ro
           AND lang_tag = :la
         LIMIT 1
    """), {"ap": body.aplicacao_id, "ro": derived_rota, "la": body.lang_tag}).mappings().first()

    if row:
        item = db.get(PageMeta, row["id"])
        item.rota = derived_rota
        item.seo_title = body.seo_title
        item.seo_description = body.seo_description
        item.canonical_url = canonical_from_app
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
            rota=derived_rota,
            lang_tag=body.lang_tag,
            seo_title=body.seo_title,
            seo_description=body.seo_description,
            canonical_url=canonical_from_app,
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

    # 3) Preparação do ZIP + status/deploy
    if not BASE_UPLOADS_URL:
        raise HTTPException(status_code=500, detail="BASE_UPLOADS_URL não configurado.")
    os.makedirs(BASE_UPLOADS_DIR, exist_ok=True)

    with engine.begin() as conn:
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
            get_deployer().dispatch_delete(domain=dominio, slug=slug_deploy or "")
            get_deployer().dispatch(
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

    ch = _fetch_children(db, [item.id])
    return PageMetaOut(**_to_out_dict(item, ch[item.id]))


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

    # Sempre recalcula canonical e rota a partir da aplicação
    with engine.begin() as conn:
        app_row = conn.execute(text("""
            SELECT
                id, dominio::text AS dominio, slug, estado::text AS estado,
                id_empresa, arquivo_zip, url_completa::text AS url_completa
            FROM global.aplicacoes
            WHERE id = :id
            LIMIT 1
        """), {"id": body.aplicacao_id or item.aplicacao_id}).mappings().first()

        if not app_row:
            raise HTTPException(status_code=404, detail="Aplicação não encontrada para o aplicacao_id informado.")

    canonical_from_app = app_row["url_completa"]
    rota_from_app = _url_path_only(canonical_from_app)

    new_ap = body.aplicacao_id or item.aplicacao_id
    new_ro = rota_from_app
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

    item.canonical_url = canonical_from_app
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
            get_deployer().dispatch_delete(domain=dominio, slug=slug_deploy or "")
            get_deployer().dispatch(
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

    ch = _fetch_children(db, [item.id])
    return PageMetaOut(**_to_out_dict(item, ch[item.id]))


# --------------------------- GET (apenas por aplicacao_id) ---------------------------
@router.get(
    "/",
    response_model=List[PageMetaOut],
    summary="(PÚBLICO) Lista Page Meta por aplicacao_id (sem rota/lang)"
)
def list_page_meta_by_app(
    aplicacao_id: int = Query(..., description="ID da aplicação"),
    db: Session = Depends(get_db),
):
    # base
    stmt = select(PageMeta).where(PageMeta.aplicacao_id == aplicacao_id).order_by(PageMeta.id.desc())
    bases = db.execute(stmt).scalars().all()
    if not bases:
        return []

    ids = [b.id for b in bases]

    # filhos em lote
    art_rows = db.execute(text("""
        SELECT page_meta_id, type, headline, description, author_name, image_urls
          FROM metadados.page_meta_article
         WHERE page_meta_id = ANY(:ids)
    """), {"ids": ids}).mappings().all()

    prod_rows = db.execute(text("""
        SELECT page_meta_id, name, description, sku, brand, price_currency, price,
               availability, item_condition, price_valid_until, image_urls
          FROM metadados.page_meta_product
         WHERE page_meta_id = ANY(:ids)
    """), {"ids": ids}).mappings().all()

    biz_rows = db.execute(text("""
        SELECT page_meta_id, business_name, phone, price_range, street, city, region, zip,
               latitude, longitude, opening_hours, image_urls, logo_url
          FROM metadados.page_meta_localbusiness
         WHERE page_meta_id = ANY(:ids)
    """), {"ids": ids}).mappings().all()

    by_art  = {r["page_meta_id"]: r for r in art_rows}
    by_prod = {r["page_meta_id"]: r for r in prod_rows}
    by_biz  = {r["page_meta_id"]: r for r in biz_rows}

    out = []
    for b in bases:
        item = {
            "id": b.id,
            "aplicacao_id": b.aplicacao_id,
            "rota": b.rota,
            "lang_tag": b.lang_tag,
            "seo_title": b.seo_title,
            "seo_description": b.seo_description,
            "canonical_url": b.canonical_url,
            "og_title": b.og_title,
            "og_description": b.og_description,
            "og_image_url": b.og_image_url,
            "og_type": b.og_type,
            "site_name": b.site_name,
            "article": None,
            "product": None,
            "localbusiness": None,
        }

        ar = by_art.get(b.id)
        if ar:
            imgs = ar["image_urls"] if isinstance(ar["image_urls"], list) else ar["image_urls"]
            if isinstance(imgs, str):
                imgs = [s for s in imgs.strip("{}").split(",") if s != ""]
            item["article"] = {
                "type": ar["type"],
                "headline": ar["headline"],
                "description": ar["description"],
                "author_name": ar["author_name"],
                "image_urls": imgs,
            }

        pr = by_prod.get(b.id)
        if pr:
            imgs = pr["image_urls"] if isinstance(pr["image_urls"], list) else None
            item["product"] = {
                "name": pr["name"],
                "description": pr["description"],
                "sku": pr["sku"],
                "brand": pr["brand"],
                "price_currency": pr["price_currency"],
                "price": pr["price"],
                "availability": pr["availability"],
                "item_condition": pr["item_condition"],
                "price_valid_until": pr["price_valid_until"],
                "image_urls": imgs,
            }

        bz = by_biz.get(b.id)
        if bz:
            imgs = bz["image_urls"] if isinstance(bz["image_urls"], list) else None
            item["localbusiness"] = {
                "business_name": bz["business_name"],
                "phone": bz["phone"],
                "price_range": bz["price_range"],
                "street": bz["street"],
                "city": bz["city"],
                "region": bz["region"],
                "zip": bz["zip"],
                "latitude": bz["latitude"],
                "longitude": bz["longitude"],
                "opening_hours": bz["opening_hours"],
                "image_urls": imgs,
                "logo_url": bz["logo_url"],
            }

        out.append(item)

    return out


@router.get("/{page_meta_id}", response_model=PageMetaOut)
def get_page_meta(
    page_meta_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    item = db.get(PageMeta, page_meta_id)
    if not item:
        raise HTTPException(status_code=404, detail="page_meta não encontrada.")
    ch = _fetch_children(db, [item.id])
    return PageMetaOut(**_to_out_dict(item, ch[item.id]))
