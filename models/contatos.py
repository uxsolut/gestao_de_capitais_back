# models/contatos.py
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class Assinatura(Base):
    __tablename__ = "assinaturas"
    __table_args__ = {"schema": "global"}

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(120), nullable=False)

    user_id = Column(
        Integer,
        ForeignKey("global.users.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Contato(Base):
    __tablename__ = "contatos"
    __table_args__ = (
        UniqueConstraint("email", name="uq_contatos_email"),
        {"schema": "global"},
    )

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("global.users.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )

    assinatura_id = Column(
        Integer,
        ForeignKey("global.assinaturas.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )

    nome = Column(String(160), nullable=False)
    telefone = Column(String(30), nullable=False)
    email = Column(String(180), nullable=False, index=True)

    supervisor = Column(Boolean, nullable=False, server_default="false", default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ContatoCodigo(Base):
    __tablename__ = "contatos_codigos"
    __table_args__ = {"schema": "global"}

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        index=True,
        server_default=func.gen_random_uuid(),
    )

    contato_id = Column(
        Integer,
        ForeignKey("global.contatos.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )

    code_hash = Column(String(64), nullable=False)  # sha256 hex (64)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
