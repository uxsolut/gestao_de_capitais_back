# -*- coding: utf-8 -*-
from sqlalchemy import BigInteger, Text, LargeBinary, Column, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.declarative import declarative_base

# Se você já tem um Base central (ex.: from database import Base), importe-o.
# Caso contrário, remova as 2 linhas abaixo e use seu Base do projeto.
Base = declarative_base()


class PaginaDinamica(Base):
    __tablename__ = "paginas_dinamicas"
    __table_args__ = (
        # constraint única existente no banco
        UniqueConstraint("dominio", "slug", name="paginas_dinamicas_dominio_slug_key"),
        # mesma check constraint do banco
        CheckConstraint(r"slug ~ '^[a-z0-9-]{1,64}$'", name="paginas_dinamicas_slug_check"),
        {"schema": "public"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # Referencia o ENUM já criado no Postgres. Não cria nem altera o tipo.
    dominio = Column(
        postgresql.ENUM(
            name="dominio_enum",
            create_type=False,          # importantíssimo: não tentar criar o tipo
        ),
        nullable=False,
    )
    slug = Column(Text, nullable=False)
    arquivo_zip = Column(LargeBinary, nullable=False)  # mapeia BYTEA
    url_completa = Column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<PaginaDinamica id={self.id} dominio={self.dominio} slug={self.slug}>"
