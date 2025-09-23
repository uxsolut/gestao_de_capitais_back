# models/empresas.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from sqlalchemy import Column, Integer, Text
from sqlalchemy.orm import relationship
from database import Base  # seu Base padrão


class Empresa(Base):
    __tablename__ = "empresas"
    __table_args__ = {"schema": "global"}  # schema correto

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(Text, nullable=False)
    descricao = Column(Text)                   # opcional
    ramo_de_atividade = Column(Text)           # opcional

    # relacionamento -> páginas dinâmicas (FK: paginas_dinamicas.id_empresa)
    paginas_dinamicas = relationship(
        "PaginaDinamica",
        back_populates="empresa",
        cascade="save-update, merge",
        passive_deletes=True,  # respeita ondelete da FK no banco
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Empresa id={self.id} nome={self.nome!r}>"
