from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Ordem(Base):
    __tablename__ = "ordens"

    id = Column(Integer, primary_key=True, index=True)
    comentario_ordem = Column(String, nullable=True)
    numero_unico = Column(String, nullable=True)
    quantidade = Column(Integer, nullable=True)
    preco = Column(Float, nullable=True)
    tipo = Column(String, nullable=True)
    conta_meta_trader = Column(String, nullable=True)

    id_robo_user = Column(Integer, ForeignKey("robos_do_user.id", ondelete="SET NULL"), nullable=True)
    id_user = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    criado_em = Column(DateTime, default=datetime.utcnow)

    # RELACIONAMENTOS
    robo_user = relationship("RobosDoUser", back_populates="ordens", foreign_keys=[id_robo_user])
    user = relationship("User", back_populates="ordens")

    def __repr__(self):
        return f"<Ordem(id={self.id}, tipo={self.tipo}, quantidade={self.quantidade}, preco={self.preco})>"
