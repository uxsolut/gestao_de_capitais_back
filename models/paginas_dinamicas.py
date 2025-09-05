# models/paginas_dinamicas.py
# -*- coding: utf-8 -*-
from sqlalchemy import BigInteger, Text, LargeBinary, Column, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects import postgresql

# use o Base central do projeto
from database import Base


class PaginaDinamica(Base):
    __tablename__ = "paginas_dinamicas"
    __table_args__ = (
        UniqueConstraint("dominio", "slug", name="paginas_dinamicas_dominio_slug_key"),
        CheckConstraint(r"slug ~ '^[a-z0-9-]{1,64}$'", name="paginas_dinamicas_slug_check"),
        {"schema": "public"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # ENUM já existente no Postgres; não criar nem listar valores aqui.
    dominio = Column(
    postgresql.ENUM(
        'pinacle.com.br', 'gestordecapitais.com',   # << valores explícitos
        name='dominio_enum',
        create_type=False,      # não recria o tipo (já existe no banco)
        native_enum=True,
        validate_strings=True,  # agora pode validar no client sem erro
    ),
    nullable=False,
)

    slug = Column(Text, nullable=False)
    arquivo_zip = Column(LargeBinary, nullable=False)  # BYTEA
    url_completa = Column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<PaginaDinamica id={self.id} dominio={self.dominio} slug={self.slug}>"
