# models/corretoras.py
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from database import Base

class Corretora(Base):
    __tablename__ = "corretoras"
    __table_args__ = {"schema": "gestor_capitais"}  # <- MESMO SCHEMA das outras tabelas

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    cnpj = Column(String, nullable=True)
    telefone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    pais = Column(String, nullable=False, default="Brasil")

    # contas.id_corretora -> corretoras.id (ambas em gestor_capitais)
    contas = relationship(
        "Conta",
        back_populates="corretora",
        primaryjoin="Corretora.id == foreign(Conta.id_corretora)",  # ajuda o SQLAlchemy
        foreign_keys="Conta.id_corretora",
        passive_deletes=True,
    )
