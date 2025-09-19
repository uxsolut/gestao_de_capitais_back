# models/ativo.py
from sqlalchemy import Column, Integer, Text, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import relationship
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
    __table_args__ = {"schema": "gestor_capitais"}  # <<< IMPORTANTE

    id = Column(Integer, primary_key=True, index=True)
    descricao = Column(Text, nullable=False)
    symbol = Column(String, nullable=False)
    pais = Column(pais_enum_pg, nullable=False)
    criado_em = Column(DateTime, server_default=func.now(), nullable=False)

    # lado 1-N com Robo
    robos = relationship("Robo", back_populates="ativo", lazy="selectin")

    def __repr__(self):
        return f"<Ativo id={self.id} symbol={self.symbol} pais={self.pais}>"
