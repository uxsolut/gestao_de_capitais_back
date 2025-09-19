# models/carteiras.py
from sqlalchemy import Column, Integer, Text, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class Carteira(Base):
    __tablename__ = "carteiras"
    __table_args__ = {"schema": "gestor_capitais"}

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(Text, nullable=False)
    id_user = Column(
        Integer,
        ForeignKey("global.users.id", ondelete="CASCADE"),  # <<< schema correto
        nullable=False,
    )

    # --------- RELACIONAMENTOS ---------
    user = relationship("User", back_populates="carteiras")

    contas = relationship(
        "Conta",
        back_populates="carteira",
        primaryjoin="foreign(Conta.id_carteira) == Carteira.id",
        foreign_keys="Conta.id_carteira",
        passive_deletes=True,
    )

    robos_do_user = relationship(
        "RoboDoUser",
        back_populates="carteira",
        primaryjoin="foreign(RoboDoUser.id_carteira) == Carteira.id",
        foreign_keys="RoboDoUser.id_carteira",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Carteira(id={self.id}, nome='{self.nome}')>"
