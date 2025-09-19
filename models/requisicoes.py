# models/requisicoes.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from database import Base

# Enum já existente no banco: gestor_capitais.tipo_de_acao
tipo_de_acao_enum = PGEnum(
    "BUY", "SELL", "CLOSE", "PATCH",
    name="tipo_de_acao",
    schema="gestor_capitais",   # <<< enum está no mesmo schema
    create_type=False,          # não recriar o tipo
)

class Requisicao(Base):
    __tablename__ = "requisicoes"
    __table_args__ = {"schema": "gestor_capitais"}  # <<< schema correto

    id = Column(Integer, primary_key=True, index=True)

    # FK -> gestor_capitais.robos(id)
    id_robo = Column(Integer, ForeignKey("gestor_capitais.robos.id"), nullable=True)

    # default CURRENT_TIMESTAMP no banco
    criado_em = Column(DateTime(timezone=False),
                       server_default=func.current_timestamp(),
                       nullable=False)

    symbol = Column(String(50), nullable=True)

    # FK -> gestor_capitais.tipo_de_ordem(id)
    id_tipo_ordem = Column(Integer, ForeignKey("gestor_capitais.tipo_de_ordem.id", ondelete="RESTRICT"), nullable=True)

    # enum gestor_capitais.tipo_de_acao
    tipo = Column(tipo_de_acao_enum, nullable=True)

    # ----------------- RELACIONAMENTOS -----------------
    robo = relationship("Robo", back_populates="requisicoes", foreign_keys=[id_robo])
    tipo_ordem = relationship("TipoDeOrdem", foreign_keys=[id_tipo_ordem])

    def __repr__(self) -> str:
        return f"<Requisicao id={self.id} tipo={self.tipo} symbol={self.symbol!r}>"

# Índices equivalentes aos do banco
Index("idx_requisicoes_symbol", Requisicao.symbol)
Index("idx_requisicoes_criado_em", Requisicao.criado_em)
Index("idx_requisicoes_id_tipo_ordem", Requisicao.id_tipo_ordem)
