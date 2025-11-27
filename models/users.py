# models/users.py
# -*- coding: utf-8 -*-
import enum
from sqlalchemy import Column, Integer, String, DateTime, Boolean, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship
from database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    cliente = "cliente"


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "global"}  # tabela está em global.users

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    senha = Column(String, nullable=False)
    cpf = Column(String, nullable=True, unique=True)

    # enum já existente no banco (user_role)
    tipo_de_user = Column(
        SAEnum(UserRole, name="user_role"),
        nullable=False,
        server_default=text("'cliente'::user_role"),
    )

    telefone = Column(String, nullable=True)

    # Relacionamentos válidos
    ordens        = relationship("Ordem",        foreign_keys="[Ordem.id_user]", back_populates="user")
    robos_do_user = relationship("RoboDoUser",   foreign_keys="[RoboDoUser.id_user]", back_populates="user")
    carteiras     = relationship("Carteira",     back_populates="user", cascade="all, delete-orphan")
    logs          = relationship("Log",          back_populates="usuario", cascade="all, delete-orphan")
    relatorios    = relationship("Relatorio",    back_populates="user")

    # NOVO: tokens de 2FA
    two_factor_tokens = relationship(
        "TwoFactorToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', tipo='{self.tipo_de_user}')>"

    @property
    def is_admin(self) -> bool:
        valor = self.tipo_de_user.value if isinstance(self.tipo_de_user, UserRole) else self.tipo_de_user
        return valor == UserRole.admin.value

    def get_contas_ativas(self):
        contas = []
        for carteira in self.carteiras:
            contas.extend([conta for conta in carteira.contas if getattr(conta, 'ativa', False)])
        return contas
