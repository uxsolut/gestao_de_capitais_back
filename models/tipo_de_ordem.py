from __future__ import annotations

from sqlalchemy import Column, BigInteger, Integer, Text, DateTime
from sqlalchemy.sql import func, text as sql_text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM as PGEnum
from database import Base


class TipoDeOrdem(Base):
    __tablename__  = "tipo_de_ordem"
    __table_args__ = {"schema": "gestor_capitais"}  # <<< schema correto

    id = Column(BigInteger, primary_key=True, index=True)  # bigint no DB
    nome_da_funcao = Column(Text, nullable=False, unique=True)
    codigo_fonte   = Column(Text, nullable=False)

    ids_robos = Column(
        ARRAY(Integer),
        nullable=False,
        server_default=sql_text("'{}'::integer[]"),
    )

    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    netting_ou_hedging = Column(
        PGEnum("Netting", "Hedging", name="netting_ou_hedging", create_type=False),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<TipoDeOrdem id={self.id} nome_da_funcao={self.nome_da_funcao!r}>"
