# models/page_meta.py
# -*- coding: utf-8 -*-
from sqlalchemy import (
    Column, Text, Integer, BigInteger, ForeignKey, UniqueConstraint,
    TIMESTAMP, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

# Se você já tem um Base central (ex.: from models.base import Base),
# pode trocar esta linha pelo seu Base.
Base = declarative_base()

class PageMeta(Base):
    __tablename__ = "page_meta"
    __table_args__ = (
        {"schema": "metadados"},
        UniqueConstraint("aplicacao_id", "rota", "lang_tag", name="uq_page_meta"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)         # BIGINT
    aplicacao_id = Column(
        Integer,
        ForeignKey("global.aplicacoes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rota = Column(Text, nullable=False, default="/")                      # '/' ou '*'
    lang_tag = Column(Text, nullable=False, default="pt-BR")              # BCP47 (pt-BR, en-US, ...)
    basic_meta = Column(JSONB, nullable=False, default=dict)
    social_og = Column(JSONB, nullable=False, default=dict)
    twitter_meta = Column(JSONB, nullable=False, default=dict)
    jsonld_base = Column(JSONB, nullable=False, default=dict)
    jsonld_product = Column(JSONB, nullable=False, default=dict)
    jsonld_article = Column(JSONB, nullable=False, default=dict)
    jsonld_localbiz = Column(JSONB, nullable=False, default=dict)
    alternates = Column(JSONB, nullable=False, default=dict)
    extras = Column(JSONB, nullable=False, default=dict)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
