from sqlalchemy import Column, Integer, Text, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


# Enum para o campo tipo_front_end
class TipoFrontEndEnum(str, enum.Enum):
    flutter = "flutter"
    web = "web"
    mobile = "mobile"
    # Adicione outros valores conforme definidos no enum do banco


# Enum para o campo tipo_aplicacao
class FrontBackEnum(str, enum.Enum):
    frontend = "frontend"
    backend = "backend"
    fullstack = "fullstack"
    # Adicione outros valores conforme definidos no enum do banco


class TipoDeAplicacao(Base):
    __tablename__ = "tipo_de_aplicacao"

    id = Column(Integer, primary_key=True, index=True)
    tipo_front_end = Column(Enum(TipoFrontEndEnum), nullable=True)
    tipo_aplicacao = Column(Enum(FrontBackEnum), nullable=True)
    descricao = Column(Text, nullable=True)
    criado_em = Column(DateTime, nullable=False, default=func.now())

    # Relacionamentos
    aplicacoes = relationship("Aplicacao", back_populates="tipo_aplicacao")
