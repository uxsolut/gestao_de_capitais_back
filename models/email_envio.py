# models/email_envio.py
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


class EmailEnvio(Base):
    __tablename__ = "email_envios"
    __table_args__ = {"schema": "global"}

    id = Column(Integer, primary_key=True, index=True)

    id_user = Column(Integer, ForeignKey("global.users.id"), nullable=False)
    tipo_user = Column(String(50), nullable=False)

    # texto / html
    tipo_conteudo = Column(String(20), nullable=False)

    email_destino = Column(String(255), nullable=False)
    assunto = Column(String(255), nullable=False)
    mensagem = Column(Text, nullable=False)

    status = Column(String(20), nullable=False, default="simulado")
    erro = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="email_envios")

    def __repr__(self) -> str:
        return (
            f"<EmailEnvio(id={self.id}, id_user={self.id_user}, "
            f"email='{self.email_destino}', status='{self.status}')>"
        )
