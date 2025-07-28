from sqlalchemy import (Column, Integer, Text, ForeignKey, String, Numeric, DateTime)
from database import Base
from sqlalchemy.orm import relationship
from datetime import datetime

class Ordem(Base):
    __tablename__ = "ordens"

    id = Column(Integer, primary_key=True, index=True)
    comentario_ordem = Column(Text, nullable=False)
    numero_unico = Column(String, nullable=True, unique=True)  # ✅ Adicionado unique constraint
    
    # ✅ Tipos de dados padronizados
    quantidade = Column(Numeric(15, 4), nullable=True)  # Maior precisão para quantidade
    preco = Column(Numeric(15, 8), nullable=True)       # Maior precisão para preço
    
    conta_meta_trader = Column(String, nullable=True)
    tipo = Column(String, nullable=True)  # buy, sell, buy_limit, sell_limit, etc.
    
    # ✅ Status da ordem
    status = Column(String(20), default="pendente", nullable=False)  # pendente, executada, cancelada, rejeitada
    
    # ✅ Relacionamentos simplificados - sem circular reference
    id_robo_user = Column(Integer, ForeignKey("robos_do_user.id"), nullable=True)
    id_user = Column(Integer, ForeignKey("users.id"), nullable=False)
    id_conta = Column(Integer, ForeignKey("contas.id"), nullable=True)  # ✅ Relacionamento direto com conta

    # ✅ Campos de auditoria
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    executado_em = Column(DateTime, nullable=True)  # ✅ Timestamp de execução
    criado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_por = Column(Integer, ForeignKey("users.id"), nullable=True)

    # ✅ Relacionamentos melhorados
    robo_user = relationship("RobosDoUser", foreign_keys=[id_robo_user])
    user = relationship("User", foreign_keys=[id_user], back_populates="ordens")
    conta = relationship("Conta", foreign_keys=[id_conta])
    
    # ✅ Relacionamentos de auditoria
    criador = relationship("User", foreign_keys=[criado_por])
    atualizador = relationship("User", foreign_keys=[atualizado_por])

    def __repr__(self):
        return f"<Ordem(id={self.id}, numero_unico='{self.numero_unico}', status='{self.status}')>"

    @property
    def valor_total(self):
        """Calcula o valor total da ordem (quantidade * preço)"""
        if self.quantidade and self.preco:
            return self.quantidade * self.preco
        return None

    @property
    def is_executada(self):
        """Verifica se a ordem foi executada"""
        return self.status == "executada" and self.executado_em is not None

