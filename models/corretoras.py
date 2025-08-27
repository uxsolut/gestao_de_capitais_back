from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from database import Base

class Corretora(Base):
    __tablename__ = "corretoras"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    cnpj = Column(String, nullable=True)
    telefone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    pais = Column(String, nullable=False, default="Brasil")  # 👈 novo campo

    contas = relationship("Conta", back_populates="corretora")
