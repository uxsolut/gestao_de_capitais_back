# models/tipo_de_ordem.py
from __future__ import annotations

from sqlalchemy import Column, BigInteger, Integer, Text, DateTime
from sqlalchemy.sql import func, text as sql_text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM as PGEnum
from database import Base


class TipoDeOrdem(Base):
    """
    Tabela: public.tipo_de_ordem

    Colunas:
      - id BIGSERIAL PK
      - nome_da_funcao TEXT UNIQUE NOT NULL
      - codigo_fonte   TEXT NOT NULL
      - ids_robos      INTEGER[] NOT NULL DEFAULT '{}'
      - criado_em      TIMESTAMPTZ NOT NULL DEFAULT now()
      - netting_ou_hedging netting_ou_hedging NOT NULL ('Netting' | 'Hedging')
    """
    __tablename__ = "tipo_de_ordem"

    id = Column(BigInteger, primary_key=True, index=True)
    nome_da_funcao = Column(Text, nullable=False, unique=True)
    codigo_fonte = Column(Text, nullable=False)

    ids_robos = Column(
        ARRAY(Integer),
        nullable=False,
        server_default=sql_text("'{}'::integer[]"),
    )

    criado_em = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Mapeia o ENUM já existente no Postgres
    netting_ou_hedging = Column(
        PGEnum("Netting", "Hedging", name="netting_ou_hedging", create_type=False),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<TipoDeOrdem id={self.id} "
            f"nome_da_funcao={self.nome_da_funcao!r} "
            f"netting_ou_hedging={self.netting_ou_hedging}>"
        )
