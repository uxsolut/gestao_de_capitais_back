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

    # ✅ Relacionamentos melhorados
    ordens = relationship("Ordem", foreign_keys="[Ordem.id_user]", back_populates="user")
    robos_do_user = relationship("RobosDoUser", foreign_keys="[RobosDoUser.id_user]", back_populates="user")
    carteiras = relationship("Carteira", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', tipo='{self.tipo_de_user}')>"

    @property
    def is_admin(self):
        """Verifica se o usuário é administrador"""
        return self.tipo_de_user == "admin"

    def get_contas_ativas(self):
        """Retorna todas as contas ativas do usuário através das carteiras"""
        contas = []
        for carteira in self.carteiras:
            contas.extend([conta for conta in carteira.contas if conta.ativa])
        return contas
