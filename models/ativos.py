# models/ativo.py
from sqlalchemy import Column, Integer, Text, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import relationship   # <<< ADICIONE ISSO
from database import Base
import enum

class PaisEnum(str, enum.Enum):
    Brasil = "Brasil"
    Canada = "Canada"
    Estados_Unidos = "Estados Unidos"
    Todos = "Todos"

pais_enum_pg = PGEnum(PaisEnum, name="pais_enum", create_type=False)

class Ativo(Base):
    __tablename__ = "ativos"

    id = Column(Integer, primary_key=True, index=True)
    descricao = Column(Text, nullable=False)
    symbol = Column(String, nullable=False)
    pais = Column(pais_enum_pg, nullable=False)
    criado_em = Column(DateTime, server_default=func.now(), nullable=False)

    # precisa existir para casar com Robo.ativo(back_populates="robos")
    robos = relationship("Robo", back_populates="ativo", lazy="selectin")

    # se você manteve o relacionamento com Relatorio:
    # relatorios = relationship("Relatorio", back_populates="ativo", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Ativo id={self.id} symbol={self.symbol} pais={self.pais}>"
