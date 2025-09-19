# models/paginas_dinamicas.py
# -*- coding: utf-8 -*-
from sqlalchemy import Integer, Text, LargeBinary, Column, CheckConstraint
from sqlalchemy.dialects import postgresql
from database import Base

class PaginaDinamica(Base):
    __tablename__ = "paginas_dinamicas"
    __table_args__ = (
        CheckConstraint(r"slug ~ '^[a-z0-9-]{1,64}$'", name="paginas_dinamicas_slug_check"),
        {"schema": "global"},  # tabela está em global.paginas_dinamicas
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ENUM já existente no schema global
    dominio = Column(
        postgresql.ENUM(
            "pinacle.com.br",
            "gestordecapitais.com",
            "tetramusic.com.br",
            name="dominio_enum",
            schema="global",
            create_type=False,
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )

    slug = Column(Text, nullable=False)
    arquivo_zip = Column(LargeBinary, nullable=False)  # BYTEA
    url_completa = Column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<PaginaDinamica id={self.id} dominio={self.dominio} slug={self.slug}>"
