# models/corretoras.py
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from database import Base

class Corretora(Base):
    __tablename__ = "corretoras"
    __table_args__ = {"schema": "gestor_capitais"}  # mesmo schema do banco

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    cnpj = Column(String, nullable=True)
    telefone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    pais = Column(String, nullable=False)  # NOT NULL conforme sua tabela

    # relacionamento inverso com Conta (FK está do lado de Conta)
    contas = relationship(
        "Conta",
        back_populates="corretora",
        passive_deletes=True,  # respeita o ON DELETE SET NULL na FK
    )
