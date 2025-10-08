# schemas/page_meta.py
# -*- coding: utf-8 -*-
import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, field_validator

class PageMetaBase(BaseModel):
    rota: str = "/"
    lang_tag: str = "pt-BR"
    basic_meta: Dict[str, Any] = {}
    social_og: Dict[str, Any] = {}
    twitter_meta: Dict[str, Any] = {}
    jsonld_base: Dict[str, Any] = {}
    jsonld_product: Dict[str, Any] = {}
    jsonld_article: Dict[str, Any] = {}
    jsonld_localbiz: Dict[str, Any] = {}
    alternates: Dict[str, Any] = {}
    extras: Dict[str, Any] = {}

    @field_validator("rota")
    @classmethod
    def _rota_ok(cls, v: str) -> str:
        v = (v or "").strip()
        if v != "*" and not v.startswith("/"):
            raise ValueError("rota deve começar com '/' ou ser '*'")
        return v

    @field_validator("lang_tag")
    @classmethod
    def _lang_ok(cls, v: str) -> str:
        v = (v or "").strip()
        # BCP47 simplificado (ex.: pt, pt-BR, en-US)
        if not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*", v):
            raise ValueError("lang_tag inválido (use BCP47, ex.: 'pt-BR')")
        return v

class PageMetaCreate(PageMetaBase):
    pass

class PageMetaOut(PageMetaBase):
    id: int
    aplicacao_id: int

    class Config:
        from_attributes = True
