# routers/page_meta.py
# -*- coding: utf-8 -*-
from typing import List, Optional
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select, text
from pydantic import BaseModel
from database import get_db
from models.page_meta import PageMeta
from schemas.page_meta import (
    PageMetaCreate, PageMetaUpdate, PageMetaOut,
    ArticleMeta, ProductMeta, LocalBusinessMeta
)

router = APIRouter(prefix="/page-meta", tags=["Page Meta"])

# ---------- GitHub Actions: workflow_dispatch ----------
async def _trigger_github_deploy(aplicacao_id: int, rota: str, lang_tag: str, page_meta_id: int):
    gh_token = os.getenv("GH_TOKEN")
    gh_owner = os.getenv("GH_OWNER")
    gh_repo = os.getenv("GH_REPO")
    gh_workflow = os.getenv("GH_WORKFLOW", "deploy.yml")
    gh_ref = os.getenv("GH_REF", "backup-state")

    if not all([gh_token, gh_owner, gh_repo, gh_workflow, gh_ref]):
        return

    url = f"https://api.github.com/repos/{gh_owner}/{gh_repo}/actions/workflows/{gh_workflow}/dispatches"
    headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"}
    payload = {
        "ref": gh_ref,
        "inputs": {
            "acao": "page_meta",
            "aplicacao_id": str(aplicacao_id),
            "rota": rota,
            "lang_tag": lang_tag,
            "page_meta_id": str(page_meta_id),
        },
    }
    timeout = httpx.Timeout(20.0, read=20.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        await client.post(url, headers=headers, json=payload)

# ---------- helpers UPSERT / DELETE filhos ----------
def _upsert_article(db: Session, page_meta_id: int, data: Optional[ArticleMeta]):
    if data is None:
        return
    # {} => deletar
    if all(getattr(data, f) is None for f in data.__fields__):
        db.execute(text("DELETE FROM metadados.page_meta_article WHERE page_meta_id = :id"), {"id": page_meta_id})
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
    if all(getattr(data, f) is None for f in data.__fields__):
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
    if all(getattr(data, f) is None for f in data.__fields__):
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
        "opening_hours": data.opening_hours,             # lista -> jsonb
        "image_urls": [str(u) for u in (data.image_urls or [])] or None,
    })

# ---------- Respostas ----------
class CreateResponse(BaseModel):
    id: int
    message: str = "page_meta criada; deploy disparado em background (se configurado)."

# ---------- POST ----------
@router.post("/", response_model=CreateResponse, status_code=status.HTTP_201_CREATED)
def create_page_meta(body: PageMetaCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    existe = db.execute(
        select(PageMeta).where(
            PageMeta.aplicacao_id == body.aplicacao_id,
            PageMeta.rota == body.rota,
            PageMeta.lang_tag == body.lang_tag,
        )
    ).scalars().first()
    if existe:
        raise HTTPException(status_code=409, detail="Já existe page_meta para (aplicacao_id, rota, lang_tag).")

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

    # upsert filhos (se vierem)
    _upsert_article(db, item.id, body.article)
    _upsert_product(db, item.id, body.product)
    _upsert_localbiz(db, item.id, body.localbusiness)
    db.commit()

    background.add_task(_trigger_github_deploy, item.aplicacao_id, item.rota, item.lang_tag, item.id)
    return CreateResponse(id=item.id)

# ---------- PUT ----------
@router.put("/{page_meta_id}", response_model=PageMetaOut)
def update_page_meta(page_meta_id: int, body: PageMetaUpdate, background: BackgroundTasks, db: Session = Depends(get_db)):
    item = db.get(PageMeta, page_meta_id)
    if not item:
        raise HTTPException(status_code=404, detail="page_meta não encontrada.")

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
        ).scalars().first()
        if conflict:
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

    # filhos (só mexe se vierem no payload)
    _upsert_article(db, item.id, body.article)
    _upsert_product(db, item.id, body.product)
    _upsert_localbiz(db, item.id, body.localbusiness)
    db.commit()

    db.refresh(item)
    background.add_task(_trigger_github_deploy, item.aplicacao_id, item.rota, item.lang_tag, item.id)
    return item

# ---------- GET (listar) ----------
@router.get("/", response_model=List[PageMetaOut])
def list_page_meta(
    aplicacao_id: Optional[int] = Query(default=None),
    rota: Optional[str] = Query(default=None),
    lang_tag: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
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

# ---------- GET (por id) ----------
@router.get("/{page_meta_id}", response_model=PageMetaOut)
def get_page_meta(page_meta_id: int, db: Session = Depends(get_db)):
    item = db.get(PageMeta, page_meta_id)
    if not item:
        raise HTTPException(status_code=404, detail="page_meta não encontrada.")
    return item
