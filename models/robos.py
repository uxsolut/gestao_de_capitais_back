# models/robo.py
from datetime import datetime
from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY

from database import Base


class Robo(Base):
    __tablename__ = "robos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(Text, nullable=False)

    # Banco: timestamp without time zone NOT NULL
    # Mantemos default em Python para garantir valor ao inserir via ORM
    criado_em = Column(DateTime, nullable=False, default=datetime.utcnow)

    # text[]
    performance = Column(ARRAY(Text), nullable=True)

    # FK opcional para ativos(id)
    id_ativo = Column(Integer, ForeignKey("ativos.id"), nullable=True)

    # -----------------
    # RELACIONAMENTOS
    # -----------------
    ativo = relationship("Ativo", foreign_keys=[id_ativo])

    logs = relationship("Log", back_populates="robo", cascade="all, delete-orphan")
    relatorios = relationship("Relatorio", back_populates="robo", cascade="all, delete-orphan")
    requisicoes = relationship("Requisicao", back_populates="robo", cascade="all, delete-orphan")
    robos_do_user = relationship("RoboDoUser", back_populates="robo", cascade="all, delete-orphan")
