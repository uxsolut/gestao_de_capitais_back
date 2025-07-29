from sqlalchemy import Column, Integer, Text, Numeric, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Ordem(Base):
    __tablename__ = "ordens"

    id = Column(Integer, primary_key=True, index=True)
    comentario_ordem = Column(Text, nullable=True)
    id_robo_user = Column(Integer, ForeignKey("robos_do_user.id", ondelete="SET NULL"), nullable=True)
    numero_unico = Column(Text, nullable=True)
    quantidade = Column(Integer, nullable=True)
    preco = Column(Numeric, nullable=True)
    id_user = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    conta_meta_trader = Column(Text, nullable=True)
    tipo = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    user = relationship("User", back_populates="ordens")
    robo_user = relationship("RobosDoUser", back_populates="ordem", foreign_keys="[Ordem.id_robo_user]")

    def __repr__(self):
        return f"<Ordem(id={self.id}, tipo='{self.tipo}', preco={self.preco})>"
