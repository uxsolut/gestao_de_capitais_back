# models/whatsapp_envio.py
# -*- coding: utf-8 -*-
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from database import Base


class WhatsAppEnvio(Base):
    __tablename__ = "whatsapp_envios"
    __table_args__ = {"schema": "global"}

    id = Column(Integer, primary_key=True, index=True)

    id_user = Column(Integer, ForeignKey("global.users.id"), nullable=False)
    tipo_user = Column(String(50), nullable=False)

    # texto / imagem (guardamos como string simples)
    tipo_mensagem = Column(String(20), nullable=False)

    telefone_destino = Column(String(20), nullable=False)
    mensagem = Column(Text, nullable=False)

    # caminho do arquivo salvo no servidor (se houver)
    imagem = Column(String(500), nullable=True)

    status = Column(String(20), nullable=False, default="simulado")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="whatsapp_envios")

    def __repr__(self) -> str:
        return (
            f"<WhatsAppEnvio(id={self.id}, id_user={self.id_user}, "
            f"tipo_mensagem='{self.tipo_mensagem}', telefone='{self.telefone_destino}')>"
        )
