# models/tipo_de_ordem.py
from sqlalchemy import (
    Column, BigInteger, Integer, Text, DateTime
)
from sqlalchemy.sql import func, text as sql_text
from sqlalchemy.dialects.postgresql import ARRAY
from database import Base


class TipoDeOrdem(Base):
    """
    Mapeia a tabela public.tipo_de_ordem

    Campos:
      - id: BIGSERIAL PK
      - nome_da_funcao: TEXT UNIQUE NOT NULL
      - codigo_fonte: TEXT NOT NULL
      - ids_robos: INTEGER[] NOT NULL DEFAULT '{}'
      - criado_em: TIMESTAMPTZ NOT NULL DEFAULT now()
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
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<TipoDeOrdem id={self.id} nome_da_funcao={self.nome_da_funcao!r}>"
