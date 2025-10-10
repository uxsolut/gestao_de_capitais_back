# schemas/page_meta.py
# -*- coding: utf-8 -*-
from typing import Optional, List
from decimal import Decimal
from datetime import datetime, date
from pydantic import BaseModel, Field, HttpUrl


# ---------------- Core ----------------
class PageMetaBase(BaseModel):
    aplicacao_id: int
    rota: str
    lang_tag: str = Field(default="pt-BR")

    # SEO
    seo_title: str
    seo_description: str
    canonical_url: HttpUrl

    # Open Graph
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image_url: Optional[HttpUrl] = None
    og_type: Optional[str] = "website"
    site_name: Optional[str] = None


# --------------- Blocos opcionais ---------------
class ArticleMeta(BaseModel):
    type: Optional[str] = None          # Article / NewsArticle / BlogPosting
    headline: Optional[str] = None
    description: Optional[str] = None
    author_name: Optional[str] = None
    date_published: Optional[datetime] = None
    date_modified: Optional[datetime] = None
    image_urls: Optional[List[HttpUrl]] = None


class ProductMeta(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sku: Optional[str] = None
    brand: Optional[str] = None
    price_currency: Optional[str] = None  # ISO 4217
    price: Optional[Decimal] = None
    availability: Optional[str] = None    # InStock
    item_condition: Optional[str] = None  # NewCondition
    price_valid_until: Optional[date] = None
    image_urls: Optional[List[HttpUrl]] = None


class LocalBusinessMeta(BaseModel):
    business_name: Optional[str] = None
    phone: Optional[str] = None
    price_range: Optional[str] = None     # "$$", "$$$"
    street: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    zip: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    opening_hours: Optional[List[str]] = None  # jsonb
    image_urls: Optional[List[HttpUrl]] = None
    logo_url: Optional[HttpUrl] = None


# --------------- Payloads ---------------
class PageMetaCreate(PageMetaBase):
    article: Optional[ArticleMeta] = None
    product: Optional[ProductMeta] = None
    localbusiness: Optional[LocalBusinessMeta] = None


class PageMetaUpdate(BaseModel):
    # chaves de busca (opcionais no PUT)
    aplicacao_id: Optional[int] = None
    rota: Optional[str] = None
    lang_tag: Optional[str] = None

    # core (opcionais)
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    canonical_url: Optional[HttpUrl] = None

    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image_url: Optional[HttpUrl] = None
    og_type: Optional[str] = None
    site_name: Optional[str] = None

    # blocos opcionais
    article: Optional[ArticleMeta] = None
    product: Optional[ProductMeta] = None
    localbusiness: Optional[LocalBusinessMeta] = None


class PageMetaOut(PageMetaBase):
    id: int
    # 🔹 expostos no output
    article: Optional[ArticleMeta] = None
    product: Optional[ProductMeta] = None
    localbusiness: Optional[LocalBusinessMeta] = None

    class Config:
        from_attributes = True
