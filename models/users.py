# -*- coding: utf-8 -*-
from datetime import datetime
import enum

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship

from database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    cliente = "cliente"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    senha = Column(String, nullable=False)
    cpf = Column(String, nullable=True, unique=True)  # ✅ Unique constraint para CPF

    # ✅ Agora usa o ENUM do PostgreSQL (user_role) em vez de String
    # server_default com cast explícito garante compatibilidade do default no banco
    tipo_de_user = Column(
        SAEnum(UserRole, name="user_role"),
        nullable=False,
        server_default=text("'cliente'::user_role"),
    )  # valores: admin, cliente

    # ✅ Relacionamentos
    ordens = relationship("Ordem", foreign_keys="[Ordem.id_user]", back_populates="user")
    robos_do_user = relationship("RoboDoUser", foreign_keys="[RoboDoUser.id_user]", back_populates="user")
    carteiras = relationship("Carteira", back_populates="user", cascade="all, delete-orphan")
    logs = relationship("Log", back_populates="usuario", cascade="all, delete-orphan")
    relatorios = relationship("Relatorio", back_populates="user")
    versoes_aplicacao = relationship("VersaoAplicacao", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', tipo='{self.tipo_de_user}')>"

    @property
    def is_admin(self) -> bool:
        """Verifica se o usuário é administrador"""
        # Suporta tanto enum quanto string (caso a sessão ainda não tenha refletido)
        valor = self.tipo_de_user.value if isinstance(self.tipo_de_user, UserRole) else self.tipo_de_user
        return valor == UserRole.admin.value

    def get_contas_ativas(self):
        """Retorna todas as contas ativas do usuário através das carteiras"""
        contas = []
        for carteira in self.carteiras:
            contas.extend([conta for conta in carteira.contas if getattr(conta, "ativa", False)])
        return contas
