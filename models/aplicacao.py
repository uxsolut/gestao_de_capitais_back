from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import relationship
from database import Base

# Atualizando o ENUM com o novo valor 'robo'
tipo_aplicacao_enum = ENUM('backend', 'frontend', 'robo', name='tipo_aplicacao', create_type=False)

class Aplicacao(Base):
    __tablename__ = "aplicacao"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(255), nullable=False)
    tipo = Column(tipo_aplicacao_enum, nullable=False)

    id_versao_aplicacao = Column(Integer, ForeignKey("versao_aplicacao.id"), nullable=False)
    id_projeto = Column(Integer, ForeignKey("projetos.id", ondelete="SET NULL"), nullable=True)

    criado_em = Column(DateTime, server_default=func.current_timestamp())
    atualizado_em = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    projeto = relationship("Projeto", back_populates="aplicacoes")
    robos_do_user = relationship("RobosDoUser", back_populates="aplicacao")
