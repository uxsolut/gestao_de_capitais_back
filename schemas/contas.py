# models/contas.py
from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Conta(Base):
    __tablename__ = "contas"

    id = Column(Integer, primary_key=True, index=True)

    # colunas conforme \d contas
    conta_meta_trader = Column(String, nullable=True)
    id_corretora      = Column(Integer, ForeignKey("corretoras.id", ondelete="SET NULL"), nullable=True)
    id_carteira       = Column(Integer, ForeignKey("carteiras.id",  ondelete="SET NULL"), nullable=True)
    nome              = Column(String, nullable=True)
    margem_total      = Column(Numeric, nullable=True)
    margem_disponivel = Column(Numeric, nullable=True)
    jwt_atual         = Column(Text, nullable=True)
    updated_at        = Column(DateTime, server_default=func.now(), onupdate=func.now())
    chave_do_token    = Column(Text, nullable=True)

    # ---------------- RELACIONAMENTOS ----------------

    # Carteira e Corretora
    carteira  = relationship(
        "Carteira",
        back_populates="contas",
        foreign_keys=[id_carteira],
        passive_deletes=True,
    )
    corretora = relationship(
        "Corretora",
        back_populates="contas",
        foreign_keys=[id_corretora],
        passive_deletes=True,
    )

    # RoboDoUser (há FK robos_do_user.id_conta -> contas.id)
    robos_do_user = relationship(
        "RoboDoUser",
        back_populates="conta",
        primaryjoin="Conta.id == foreign(RoboDoUser.id_conta)",
        foreign_keys="RoboDoUser.id_conta",
        passive_deletes=True,
        # use cascade se a Conta for 'dona' do vínculo; senão, remova:
        # cascade="all, delete-orphan",
    )

    # Logs (há FK logs.id_conta -> contas.id)
    logs = relationship(
        "Log",
        back_populates="conta",
        primaryjoin="Conta.id == foreign(Log.id_conta)",
        foreign_keys="Log.id_conta",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Conta id={self.id} nome={self.nome}>"
