# models/projeto.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, text
from sqlalchemy.orm import relationship
from database import Base

class Projeto(Base):
    __tablename__ = "projetos"
    __table_args__ = {"schema": "global"}  # tabela está em global.projetos

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(255), nullable=False)

    atualizado_em = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    # FK para global.paginas_dinamicas.id
    id_pagina_em_uso = Column(
        Integer,
        ForeignKey("global.paginas_dinamicas.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    pagina_em_uso = relationship(
        "PaginaDinamica",
        primaryjoin="foreign(Projeto.id_pagina_em_uso) == PaginaDinamica.id",
        lazy="joined",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<Projeto id={self.id} nome={self.nome} id_pagina_em_uso={self.id_pagina_em_uso}>"
