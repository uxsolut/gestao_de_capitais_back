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

# ===== Enums já existentes no Postgres =====
# (create_type=False para não tentar recriar)

dominio_enum = postgresql.ENUM(
    "pinacle.com.br",
    "gestordecapitais.com",
    "tetramusic.com.br",
    name="dominio_enum",
    schema="global",
    create_type=False,
    native_enum=True,
    validate_strings=True,
)

frontback_enum = postgresql.ENUM(
    "frontend",
    "backend",
    "fullstack",
    name="frontbackenum",
    schema="gestor_capitais",
    create_type=False,
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
    create_type=False,
    native_enum=True,
    validate_strings=True,
)

servidor_enum = postgresql.ENUM(
    "teste 1",
    "teste 2",
    name="servidor_enum",
    schema="global",
    create_type=False,
    native_enum=True,
    validate_strings=True,
)

# ===== Novo ENUM: tipo_api_enum (global) =====
tipo_api_enum = postgresql.ENUM(
    "get",
    "post",
    "put",
    "delete",
    "cron_job",
    "webhook",
    "websocket",
    name="tipo_api_enum",
    schema="global",
    create_type=False,
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

    # Agora todas as colunas (exceto id) permitem NULL
    dominio = Column(dominio_enum, nullable=True)

    # slug pode ser NULL (homepage por domínio/estado)
    slug = Column(Text, nullable=True)

    # BYTEA
    arquivo_zip = Column(LargeBinary, nullable=True)

    url_completa = Column(Text, nullable=True)

    # ENUMs
    front_ou_back = Column(frontback_enum, nullable=True)  # gestor_capitais.frontbackenum
    estado = Column(estado_enum, nullable=True)            # global.estado_enum

    # FK para global.empresas(id) com ON DELETE SET NULL
    id_empresa = Column(
        Integer,
        ForeignKey("global.empresas.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Booleana (default false), porém aceita NULL no banco atual
    precisa_logar = Column(Boolean, nullable=True, server_default=text("false"))

    # ===== Novas colunas =====
    anotacoes = Column(Text, nullable=True)

    # Arrays de texto
    dados_de_entrada = Column(postgresql.ARRAY(Text), nullable=True)
    tipos_de_retorno = Column(postgresql.ARRAY(Text), nullable=True)

    rota = Column(Text, nullable=True)
    porta = Column(Text, nullable=True)

    servidor = Column(servidor_enum, nullable=True)  # global.servidor_enum

    # Novo campo ENUM com o tipo criado acima
    tipo_api = Column(tipo_api_enum, nullable=True)  # global.tipo_api_enum

    def __repr__(self) -> str:
        return (
            f"<Aplicacao id={self.id} dominio={self.dominio} slug={self.slug} "
            f"front_ou_back={self.front_ou_back} estado={self.estado} "
            f"precisa_logar={self.precisa_logar} id_empresa={self.id_empresa} "
            f"servidor={self.servidor} tipo_api={self.tipo_api}>"
        )
