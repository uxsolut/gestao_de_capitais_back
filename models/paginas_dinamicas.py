# models/paginas_dinamicas.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from sqlalchemy import (
    Column, Integer, Text, LargeBinary, CheckConstraint, ForeignKey
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import relationship

from database import Base


# ============================
# Tipos ENUM já existentes
# (não recriar: create_type=False)
# ============================
dominio_enum = PGEnum(
    "pinacle.com.br",
    "gestordecapitais.com",
    "tetramusic.com.br",
    name="dominio_enum",
    schema="global",
    create_type=False,
    native_enum=True,
    validate_strings=True,
)

frontback_enum = PGEnum(
    "frontend",
    "backend",
    "fullstack",
    name="frontbackenum",
    schema="global",          # <-- ajustado para o schema global
    create_type=False,
    native_enum=True,
    validate_strings=True,
)

estado_enum = PGEnum(
    "producao",
    "beta",
    "dev",
    "desativado",
    name="estado_enum",
    schema="global",
    create_type=False,
    native_enum=True,
    validate_strings=True,
)


class PaginaDinamica(Base):
    __tablename__ = "paginas_dinamicas"
    __table_args__ = (
        CheckConstraint(r"slug ~ '^[a-z0-9-]{1,64}$'", name="paginas_dinamicas_slug_check"),
        {"schema": "global"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    dominio = Column(dominio_enum, nullable=False)
    slug = Column(Text, nullable=False)
    arquivo_zip = Column(LargeBinary, nullable=False)  # BYTEA
    url_completa = Column(Text, nullable=False)

    front_ou_back = Column(frontback_enum, nullable=True)
    estado = Column(estado_enum, nullable=True)

    # ---- NOVO: vínculo com Empresa ----
    id_empresa = Column(
        Integer,
        ForeignKey("global.empresas.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # relação inversa
    empresa = relationship("Empresa", back_populates="paginas_dinamicas")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PaginaDinamica id={self.id} dominio={self.dominio} "
            f"slug={self.slug} front_ou_back={self.front_ou_back} estado={self.estado}>"
        )
