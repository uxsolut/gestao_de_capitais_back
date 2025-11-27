# models/two_factor_tokens.py
# -*- coding: utf-8 -*-
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import relationship

from database import Base


class TwoFactorToken(Base):
    """
    Tokens de verificação em duas etapas (2FA) enviados por WhatsApp.

    Tabela: global.two_factor_tokens
    """
    __tablename__ = "two_factor_tokens"
    __table_args__ = {"schema": "global"}

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("global.users.id"), nullable=False)

    # hash do código (não armazenamos o código em texto puro)
    code_hash = Column(String(255), nullable=False)

    # quando expira o código
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # se já foi usado com sucesso
    used = Column(Boolean, nullable=False, server_default=text("false"))

    # quantidade de tentativas
    attempts = Column(Integer, nullable=False, server_default=text("0"))

    # data de criação
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    # relação com usuário
    user = relationship("User", back_populates="two_factor_tokens")

    def __repr__(self) -> str:
        return f"<TwoFactorToken(id={self.id}, user_id={self.user_id}, used={self.used})>"
