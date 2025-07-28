from sqlalchemy import Column, Integer, String, Text, LargeBinary, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Robos(Base):
    __tablename__ = "robos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    descricao = Column(Text, nullable=True)
    arquivo_robo = Column(LargeBinary, nullable=True)
    
    # ✅ Campos de controle
    ativo = Column(Boolean, default=True, nullable=False)
    versao = Column(String, nullable=True)
    tipo = Column(String, nullable=True)  # scalper, swing, day_trade, etc.
    
    # ✅ Campos de auditoria
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    criado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_por = Column(Integer, ForeignKey("users.id"), nullable=True)

    # ✅ Relacionamentos melhorados
    robos_do_user = relationship("RobosDoUser", back_populates="robo")
    requisicoes = relationship("Requisicao", back_populates="robo")  # ✅ Relacionamento com requisições
    
    # ✅ Relacionamentos de auditoria
    criador = relationship("User", foreign_keys=[criado_por])
    atualizador = relationship("User", foreign_keys=[atualizado_por])

    def __repr__(self):
        return f"<Robos(id={self.id}, nome='{self.nome}', ativo={self.ativo})>"

    @property
    def usuarios_ativos(self):
        """Retorna o número de usuários ativos usando este robô"""
        return len([r for r in self.robos_do_user if r.is_operacional])

    def get_requisicoes_pendentes(self):
        """Retorna requisições não aprovadas para este robô"""
        return [r for r in self.requisicoes if not r.aprovado]

