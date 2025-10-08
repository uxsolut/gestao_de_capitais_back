# schemas/page_meta.py
# -*- coding: utf-8 -*-
import re
from typing import Any, Dict
from pydantic import BaseModel

_LANG_RE = re.compile(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*")

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

    # Validaremos rota/lang_tag no router para evitar dependência de decorators de versão

class PageMetaCreate(PageMetaBase):
    pass

class PageMetaOut(PageMetaBase):
    id: int
    aplicacao_id: int

    class Config:
        # v1: orm_mode; v2: from_attributes
        orm_mode = True
        from_attributes = True
