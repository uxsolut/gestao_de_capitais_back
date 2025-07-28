from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship
from database import Base

class Projeto(Base):
    __tablename__ = "projetos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(255), nullable=False)

    criado_em = Column(DateTime, server_default=func.current_timestamp())
    atualizado_em = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    aplicacoes = relationship("Aplicacao", back_populates="projeto")
