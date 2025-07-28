from sqlalchemy import (Column, Integer, ForeignKey, LargeBinary, Boolean, DateTime, String)
from database import Base
from sqlalchemy.orm import relationship
from datetime import datetime

class RobosDoUser(Base):
    __tablename__ = "robos_do_user"

    id = Column(Integer, primary_key=True, index=True)
    id_user = Column(Integer, ForeignKey("users.id"), nullable=False)
    id_robo = Column(Integer, ForeignKey("robos.id"), nullable=False)
    arquivo_cliente = Column(LargeBinary, nullable=True)

    # ✅ Status padronizados com enum-like approach
    ligado = Column(Boolean, default=False, nullable=False)
    ativo = Column(Boolean, default=False, nullable=False)
    tem_requisicao = Column(Boolean, default=False, nullable=False)
    
    # ✅ Status geral para controle de estado
    status = Column(String(20), default="inativo", nullable=False)  # inativo, ativo, pausado, erro

    # ✅ Relacionamentos simplificados - removido relacionamento circular com Ordem
    id_carteira = Column(Integer, ForeignKey("carteiras.id"), nullable=True)
    id_conta = Column(Integer, ForeignKey("contas.id"), nullable=True)

    # ✅ Campos de auditoria adicionados
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    criado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_por = Column(Integer, ForeignKey("users.id"), nullable=True)

    # ✅ Relacionamentos melhorados
    user = relationship("User", foreign_keys=[id_user], back_populates="robos_do_user")
    carteira = relationship("Carteira")
    conta = relationship("Conta")
    robo = relationship("Robo", back_populates="robos_do_user")
    
    # ✅ Relacionamentos de auditoria
    criador = relationship("User", foreign_keys=[criado_por])
    atualizador = relationship("User", foreign_keys=[atualizado_por])

    def __repr__(self):
        return f"<RobosDoUser(id={self.id}, user_id={self.id_user}, robo_id={self.id_robo}, status='{self.status}')>"

    @property
    def is_operacional(self):
        """Verifica se o robô está operacional (ligado e ativo)"""
        return self.ligado and self.ativo and self.status == "ativo"
