# models/empresas.py
# -*- coding: utf-8 -*-
from sqlalchemy import Integer, Text, Column
from database import Base

class Empresa(Base):
    __tablename__ = "empresas"
    __table_args__ = ({"schema": "global"},)

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(Text, nullable=False)
    descricao = Column(Text, nullable=True)
    ramo_de_atividade = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Empresa id={self.id} nome={self.nome}>"
