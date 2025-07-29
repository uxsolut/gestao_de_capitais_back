from sqlalchemy import Column, Integer, Text, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class Carteira(Base):
    __tablename__ = "carteiras"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(Text, nullable=False)
    id_user = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Relacionamentos
    user = relationship("User", back_populates="carteiras")
    contas = relationship("Conta", back_populates="carteira", cascade="all, delete-orphan")
    robos_do_user = relationship("RobosDoUser", back_populates="carteira")

    def __repr__(self):
        return f"<Carteira(id={self.id}, nome='{self.nome}')>"
