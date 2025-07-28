from sqlalchemy import (Column, Integer, String, Text, Numeric, ForeignKey, ARRAY, DateTime, Boolean)
from database import Base
from sqlalchemy.orm import relationship
from datetime import datetime

class Requisicao(Base):
    __tablename__ = "requisicoes"

    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(String, nullable=False)
    comentario_ordem = Column(Text, nullable=True)
    symbol = Column(String, nullable=True)
    quantidade = Column(Integer, nullable=True)
    preco = Column(Numeric(12, 2), nullable=True)

    # ✅ Campo aprovado adicionado conforme conhecimento
    aprovado = Column(Boolean, default=False, nullable=False)

    id_robo = Column(Integer, ForeignKey("robos.id"), nullable=True)
    ids_contas = Column(ARRAY(Integer), nullable=True)  # array de ids, FK lógica

    # ✅ Campos de auditoria adicionados
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    criado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_por = Column(Integer, ForeignKey("users.id"), nullable=True)

    # ✅ Relacionamentos melhorados
    robo = relationship("Robos", back_populates="requisicoes")
    criador = relationship("User", foreign_keys=[criado_por])
    atualizador = relationship("User", foreign_keys=[atualizado_por])

    def __repr__(self):
        return f"<Requisicao(id={self.id}, tipo='{self.tipo}', aprovado={self.aprovado})>"

