# models/page_meta.py
# -*- coding: utf-8 -*-
from sqlalchemy import (
    Column, Text, BigInteger, UniqueConstraint, DateTime, func
)
from sqlalchemy.orm import declarative_base

# Caso você já tenha um Base central (ex.: from database import Base), use-o aqui:
# from database import Base
Base = declarative_base()


class PageMeta(Base):
    __tablename__ = "page_meta"
    __table_args__ = (
        UniqueConstraint("aplicacao_id", "rota", "lang_tag", name="page_meta_aplicacao_id_rota_lang_tag_key"),
        {"schema": "metadados"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    aplicacao_id = Column(BigInteger, nullable=False)
    rota = Column(Text, nullable=False)
    lang_tag = Column(Text, nullable=False)

    # SEO
    seo_title = Column(Text, nullable=False)
    seo_description = Column(Text, nullable=False)
    canonical_url = Column(Text, nullable=False)

    # OG (opcionais com fallback na renderização)
    og_title = Column(Text, nullable=True)
    og_description = Column(Text, nullable=True)
    og_image_url = Column(Text, nullable=True)
    og_type = Column(Text, nullable=True, default="website")
    site_name = Column(Text, nullable=True)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
