from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Aplicacao(Base):
    __tablename__ = "aplicacao"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    id_versao_aplicacao = Column(Integer, ForeignKey("versao_aplicacao.id"), nullable=True)
    criado_em = Column(DateTime, default=func.now())
    atualizado_em = Column(DateTime, default=func.now(), onupdate=func.now())

    id_projeto = Column(Integer, ForeignKey("projetos.id"), nullable=True)
    id_tipo_aplicacao = Column(Integer, ForeignKey("tipo_de_aplicacao.id"), nullable=True)

    tipo = Column(String, nullable=True)
    qual_finalidade = Column(Text, nullable=True)

    # Relacionamentos
    versao_aplicacao = relationship(
        "VersaoAplicacao",
        foreign_keys=[id_versao_aplicacao],  # 👈 necessário
        uselist=False
    )

    versoes = relationship(
        "VersaoAplicacao",
        back_populates="aplicacao",
        foreign_keys="[VersaoAplicacao.id_aplicacao]"  # 👈 necessário
    )

    projeto = relationship("Projeto", back_populates="aplicacoes")
    tipo_aplicacao = relationship("TipoDeAplicacao", back_populates="aplicacoes")
    logs = relationship("Log", back_populates="aplicacao", cascade="all, delete-orphan")
    robos_do_user = relationship("RoboDoUser", back_populates="aplicacao")

    def __repr__(self):
        return f"<Aplicacao(id={self.id}, nome='{self.nome}')>"
