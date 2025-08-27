from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY
from datetime import datetime
from database import Base

class Robo(Base):
    __tablename__ = "robos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(Text, nullable=False)
    criado_em = Column(DateTime, nullable=False, default=datetime.utcnow)
    performance = Column(ARRAY(Text), nullable=True)
    id_ativo = Column(Integer, ForeignKey("ativos.id"))

    ativo = relationship("Ativo", foreign_keys=[id_ativo])
    relatorios = relationship("Relatorio", back_populates="robo")

    logs = relationship("Log", back_populates="robo", cascade="all, delete-orphan")
    relatorios = relationship("Relatorio", back_populates="robo", cascade="all, delete-orphan")
    requisicoes = relationship("Requisicao", back_populates="robo", cascade="all, delete-orphan")
    robos_do_user = relationship("RoboDoUser", back_populates="robo", cascade="all, delete-orphan")
