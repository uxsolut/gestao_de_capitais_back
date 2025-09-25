# models/aplicacoes.py
# -*- coding: utf-8 -*-
from sqlalchemy import (
    Integer,
    Text,
    LargeBinary,
    Column,
    CheckConstraint,
    ForeignKey,
    Boolean,
    text,
)
from sqlalchemy.dialects import postgresql

from database import Base

# Tipos ENUM já existentes no Postgres
frontback_enum = postgresql.ENUM(
    "frontend",
    "backend",
    "fullstack",
    name="frontbackenum",
    schema="gestor_capitais",
    create_type=False,        # o tipo já existe no banco
    native_enum=True,
    validate_strings=True,
)

estado_enum = postgresql.ENUM(
    "producao",
    "beta",
    "dev",
    "desativado",
    name="estado_enum",
    schema="global",
    create_type=False,        # o tipo já existe no banco
    native_enum=True,
    validate_strings=True,
)

class Aplicacao(Base):
    __tablename__ = "aplicacoes"
    __table_args__ = (
        CheckConstraint(r"slug ~ '^[a-z0-9-]{1,64}$'", name="aplicacoes_slug_check"),
        {"schema": "global"},  # tabela está em global.aplicacoes
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

    # Colunas (ENUMs)
    front_ou_back = Column(frontback_enum, nullable=True)  # gestor_capitais.frontbackenum
    estado        = Column(estado_enum,    nullable=True)  # global.estado_enum

    # Nova coluna booleana
    precisa_logar = Column(Boolean, nullable=False, server_default=text("false"))

    # FK para global.empresas(id) com ON DELETE SET NULL
    id_empresa = Column(
        Integer,
        ForeignKey("global.empresas.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Aplicacao id={self.id} dominio={self.dominio} slug={self.slug} "
            f"front_ou_back={self.front_ou_back} estado={self.estado} "
            f"precisa_logar={self.precisa_logar} "
            f"id_empresa={self.id_empresa}>"
        )
