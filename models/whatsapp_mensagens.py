# models/whatsapp_mensagens.py
# -*- coding: utf-8 -*-

from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
)
from sqlalchemy.dialects.postgresql import JSONB

from database import Base  # mesmo Base que você usa nas outras tabelas


class WhatsAppMensagem(Base):
    __tablename__ = "whatsapp_mensagens"
    __table_args__ = {"schema": "global"}  # importante por causa do schema

    id = Column(Integer, primary_key=True, index=True)

    instance_id = Column(String(64), nullable=True)
    message_id = Column(String(64), nullable=True, unique=True, index=True)

    phone = Column(String(32), nullable=False, index=True)
    sender_name = Column(String(255), nullable=True)
    chat_name = Column(String(255), nullable=True)

    texto = Column(Text, nullable=True)
    status = Column(String(32), nullable=True)
    from_me = Column(Boolean, nullable=False, default=False)

    momment = Column(DateTime(timezone=True), nullable=True, index=True)

    # JSON cru da Z-API
    raw_payload = Column(JSONB, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
