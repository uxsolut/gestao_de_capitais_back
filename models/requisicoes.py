# models/requisicoes.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from database import Base

# Enum já existente no banco: public.tipo_de_acao
tipo_de_acao_enum = PGEnum(
    'BUY', 'SELL', 'CLOSE', 'PATCH',
    name='tipo_de_acao',
    create_type=False,  # o tipo já foi criado via SQL/migration
)

class Requisicao(Base):
    __tablename__ = "requisicoes"

    id = Column(Integer, primary_key=True, index=True)

    # FK -> robos(id)
    id_robo = Column(Integer, ForeignKey("robos.id"), nullable=True)

    # timestamp: usa default do banco (CURRENT_TIMESTAMP)
    criado_em = Column(DateTime(timezone=False),
                       server_default=func.current_timestamp(),
                       nullable=False)

    # varchar(50)
    symbol = Column(String(50), nullable=True)

    # FK -> tipo_de_ordem(id)
    id_tipo_ordem = Column(Integer, ForeignKey("tipo_de_ordem.id", ondelete="RESTRICT"), nullable=True)

    # enum public.tipo_de_acao
    tipo = Column(tipo_de_acao_enum, nullable=True)  # deixe True para casar com o schema atual

    # --- relacionamentos ---
    robo = relationship("Robo", back_populates="requisicoes", foreign_keys=[id_robo])
    tipo_ordem = relationship("TipoDeOrdem", foreign_keys=[id_tipo_ordem])

    def __repr__(self) -> str:
        return f"<Requisicao id={self.id} tipo={self.tipo} symbol={self.symbol!r}>"

# Índices (correspondem aos que estão no banco)
Index("idx_requisicoes_symbol", Requisicao.symbol)
Index("idx_requisicoes_criado_em", Requisicao.criado_em)
Index("idx_requisicoes_id_tipo_ordem", Requisicao.id_tipo_ordem)
