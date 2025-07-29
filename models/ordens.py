from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Ordem(Base):
    __tablename__ = "ordens"

    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(String, nullable=False)  # exemplo: 'compra' ou 'venda'
    comentario_ordem = Column(String, nullable=True)
    symbol = Column(String, nullable=False)
    quantidade = Column(Integer, nullable=False)
    preco = Column(Float, nullable=False)

    # FK para o robô do usuário
    id_robo_user = Column(Integer, ForeignKey("robos_do_user.id"), nullable=False)
    robo_user = relationship("RobosDoUser", back_populates="ordens")

    # FK para o usuário criador da ordem
    id_user = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="ordens")

    # Auditoria
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    criado_por = Column(Integer, nullable=True)
    atualizado_por = Column(Integer, nullable=True)

    def __repr__(self):
        return f"<Ordem(id={self.id}, tipo={self.tipo}, symbol={self.symbol}, preco={self.preco})>"
