from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, LargeBinary
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class VersaoAplicacao(Base):
    __tablename__ = "versao_aplicacao"

    id = Column(Integer, primary_key=True, index=True)
    descricao = Column(Text, nullable=False)
    arquivo = Column(LargeBinary, nullable=True)
    data_versao = Column(DateTime, default=func.now())

    id_user = Column(Integer, ForeignKey("users.id"))
    id_aplicacao = Column(Integer, ForeignKey("aplicacao.id"))

    criado_em = Column(DateTime, default=func.now())

    # Relacionamentos
    user = relationship("User", back_populates="versoes_aplicacao")

    # N -> 1 com Aplicacao (bate com Aplicacao.versoes)
    aplicacao = relationship(
        "Aplicacao",
        back_populates="versoes",
        foreign_keys=[id_aplicacao],
    )

    def __repr__(self):
        return f"<VersaoAplicacao(id={self.id}, descricao='{self.descricao}')>"
