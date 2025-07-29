from sqlalchemy import Column, Integer, String, Text, Numeric, ForeignKey, ARRAY, DateTime
from database import Base
from sqlalchemy.orm import relationship
from datetime import datetime

class Requisicao(Base):
    __tablename__ = "requisicoes"

    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(Text, nullable=False)
    comentario_ordem = Column(Text, nullable=False)
    quantidade = Column(Integer, nullable=True)
    preco = Column(Numeric(12, 2), nullable=True)

    id_robo = Column(Integer, ForeignKey("robos.id", ondelete="CASCADE"), nullable=True)
    id_ativo = Column(Integer, ForeignKey("ativos.id"), nullable=True)
    ids_contas = Column(ARRAY(Integer), nullable=True)

    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)


    # Relacionamentos existentes no banco
    robo = relationship("Robo", back_populates="requisicoes", foreign_keys=[id_robo])

    def __repr__(self):
        return f"<Requisicao(id={self.id}, tipo='{self.tipo}')>"
