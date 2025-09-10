from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Aplicacao(Base):
    __tablename__ = "aplicacao"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)

    # ponteiro para a versão "ativa" (opcional)
    id_versao_aplicacao = Column(Integer, ForeignKey("versao_aplicacao.id"), nullable=True)

    criado_em = Column(DateTime, default=func.now())
    atualizado_em = Column(DateTime, default=func.now(), onupdate=func.now())

    id_projeto = Column(Integer, ForeignKey("projetos.id"), nullable=True)
    id_tipo_aplicacao = Column(Integer, ForeignKey("tipo_de_aplicacao.id"), nullable=True)

    # metadados descritivos (opcionais)
    tipo = Column(String, nullable=True)
    qual_finalidade = Column(Text, nullable=True)

    # ---------- RELACIONAMENTOS ----------
    # versão ativa (1-1 opcional) — sem back_populates (seu VersaoAplicacao não define o lado reverso)
    versao_aplicacao = relationship(
        "VersaoAplicacao",
        foreign_keys=[id_versao_aplicacao],
        uselist=False,
    )

    # histórico de versões (1-N) — bate com VersaoAplicacao.aplicacao
    versoes = relationship(
        "VersaoAplicacao",
        back_populates="aplicacao",
        foreign_keys="VersaoAplicacao.id_aplicacao",
        cascade="all, delete-orphan",
    )

    projeto = relationship("Projeto", back_populates="aplicacoes")
    tipo_aplicacao = relationship("TipoDeAplicacao", back_populates="aplicacoes")

    logs = relationship("Log", back_populates="aplicacao", cascade="all, delete-orphan")

    # relação com RoboDoUser (1-N)
    robos_do_user = relationship("RoboDoUser", back_populates="aplicacao")

    def __repr__(self):
        return f"<Aplicacao(id={self.id}, nome='{self.nome}')>"
