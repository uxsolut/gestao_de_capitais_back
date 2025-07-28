from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, DateTime, Boolean
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Conta(Base):
    __tablename__ = "contas"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)  # ✅ Nome obrigatório
    conta_meta_trader = Column(String, nullable=True, unique=True)  # ✅ Unique constraint
    
    # ✅ Relacionamentos com constraints adequados
    id_corretora = Column(Integer, ForeignKey("corretoras.id", ondelete="SET NULL"), nullable=True)
    id_carteira = Column(Integer, ForeignKey("carteiras.id", ondelete="SET NULL"), nullable=True)

    # ✅ Campos financeiros com precisão adequada
    margem_total = Column(Numeric(15, 2), nullable=True, default=0.00)
    margem_disponivel = Column(Numeric(15, 2), nullable=True, default=0.00)
    margem_utilizada = Column(Numeric(15, 2), nullable=True, default=0.00)  # ✅ Campo adicional
    
    # ✅ Campos de controle
    ativa = Column(Boolean, default=True, nullable=False)
    status = Column(String(20), default="ativa", nullable=False)  # ativa, inativa, bloqueada, suspensa
    
    # ✅ Campos de auditoria
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    criado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_por = Column(Integer, ForeignKey("users.id"), nullable=True)

    # ✅ Relacionamentos melhorados
    corretora = relationship("Corretora", back_populates="contas")
    carteira = relationship("Carteira", back_populates="contas")
    
    # ✅ Relacionamento com ordens
    ordens = relationship("Ordem", foreign_keys="[Ordem.id_conta]", back_populates="conta")
    
    # ✅ Relacionamentos de auditoria
    criador = relationship("User", foreign_keys=[criado_por])
    atualizador = relationship("User", foreign_keys=[atualizado_por])

    def __repr__(self):
        return f"<Conta(id={self.id}, nome='{self.nome}', status='{self.status}')>"

    @property
    def margem_livre(self):
        """Calcula a margem livre (disponível - utilizada)"""
        if self.margem_disponivel and self.margem_utilizada:
            return self.margem_disponivel - self.margem_utilizada
        return self.margem_disponivel or 0

    @property
    def percentual_utilizacao(self):
        """Calcula o percentual de utilização da margem"""
        if self.margem_total and self.margem_total > 0 and self.margem_utilizada:
            return (self.margem_utilizada / self.margem_total) * 100
        return 0

    def pode_operar(self, valor_necessario):
        """Verifica se a conta pode operar com o valor especificado"""
        return (self.ativa and 
                self.status == "ativa" and 
                self.margem_livre >= valor_necessario)

