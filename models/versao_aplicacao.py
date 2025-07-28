from sqlalchemy import Column, Integer, Text, LargeBinary, DateTime, ForeignKey, func
from database import Base
from sqlalchemy.orm import relationship  # se quiser usar relacionamento

class VersaoAplicacao(Base):
    __tablename__ = "versao_aplicacao"

    id = Column(Integer, primary_key=True, index=True)
    descricao = Column(Text, nullable=False)
    arquivo = Column(LargeBinary)
    data_versao = Column(DateTime, server_default=func.current_timestamp())
    id_user = Column(Integer, ForeignKey("users.id"), nullable=False)
    id_aplicacao = Column(Integer, ForeignKey("aplicacao.id"), nullable=True)  # novo campo
    criado_em = Column(DateTime, server_default=func.current_timestamp())

    # Relacionamento (opcional)
    aplicacao = relationship("Aplicacao", backref="versoes", foreign_keys=[id_aplicacao])
