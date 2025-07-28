from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    senha = Column(String, nullable=False)
    cpf = Column(String, nullable=True, unique=True)  # ✅ Unique constraint para CPF
    
    # ✅ Relacionamento com conta corrigido - removido id_conta direto
    tipo_de_user = Column(String, nullable=False, default="cliente")  # admin, cliente
    
    # ✅ Campos de controle
    ativo = Column(Boolean, default=True, nullable=False)
    email_verificado = Column(Boolean, default=False, nullable=False)
    
    # ✅ Campos de auditoria
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    ultimo_login = Column(DateTime, nullable=True)
    criado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_por = Column(Integer, ForeignKey("users.id"), nullable=True)

    # ✅ Relacionamentos melhorados
    ordens = relationship("Ordem", foreign_keys="[Ordem.id_user]", back_populates="user")
    robos_do_user = relationship("RobosDoUser", foreign_keys="[RobosDoUser.id_user]", back_populates="user")
    carteiras = relationship("Carteira", back_populates="user", cascade="all, delete-orphan")
    
    # ✅ Relacionamentos de auditoria
    criador = relationship("User", foreign_keys=[criado_por], remote_side=[id])
    atualizador = relationship("User", foreign_keys=[atualizado_por], remote_side=[id])
    
    # ✅ Relacionamentos criados por este usuário (auditoria reversa)
    requisicoes_criadas = relationship("Requisicao", foreign_keys="[Requisicao.criado_por]")
    ordens_criadas = relationship("Ordem", foreign_keys="[Ordem.criado_por]")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', tipo='{self.tipo_de_user}')>"

    @property
    def is_admin(self):
        """Verifica se o usuário é administrador"""
        return self.tipo_de_user == "admin"

    @property
    def is_ativo(self):
        """Verifica se o usuário está ativo"""
        return self.ativo

    def pode_operar(self):
        """Verifica se o usuário pode realizar operações"""
        return self.ativo and self.email_verificado

    def get_contas_ativas(self):
        """Retorna todas as contas ativas do usuário através das carteiras"""
        contas = []
        for carteira in self.carteiras:
            contas.extend([conta for conta in carteira.contas if conta.ativa])
        return contas

