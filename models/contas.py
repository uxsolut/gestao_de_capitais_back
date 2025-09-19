# models/contas.py
from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, Text, DateTime, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Conta(Base):
    __tablename__ = "contas"
    __table_args__ = {"schema": "gestor_capitais"}  # <<< MESMO SCHEMA DO robos_do_user

    id = Column(Integer, primary_key=True, index=True)

    conta_meta_trader = Column(String, nullable=True)
    id_corretora      = Column(Integer, ForeignKey("gestor_capitais.corretoras.id", ondelete="SET NULL"), nullable=True)
    id_carteira       = Column(Integer, ForeignKey("gestor_capitais.carteiras.id",  ondelete="SET NULL"), nullable=True)

    nome              = Column(Text, nullable=True)
    margem_total      = Column(Numeric, nullable=True)
    margem_disponivel = Column(Numeric, nullable=True)
    jwt_atual         = Column(Text, nullable=True)

    updated_at     = Column(DateTime(timezone=False),
                            server_default=func.current_timestamp(),
                            onupdate=func.current_timestamp(),
                            nullable=True)
    chave_do_token = Column(Text, nullable=True)

    # ---------------- RELACIONAMENTOS ----------------
    carteira = relationship(
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

    # FK existe: gestor_capitais.robos_do_user.id_conta -> gestor_capitais.contas.id
    robos_do_user = relationship(
        "RoboDoUser",
        back_populates="conta",
        primaryjoin="Conta.id == foreign(RoboDoUser.id_conta)",
        foreign_keys="RoboDoUser.id_conta",
        passive_deletes=True,
    )

    # logs.id_conta -> contas.id (ambos em gestor_capitais)
    logs = relationship(
        "Log",
        back_populates="conta",
        primaryjoin="Conta.id == foreign(Log.id_conta)",
        foreign_keys="Log.id_conta",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Conta id={self.id} nome={self.nome!r} conta_meta_trader={self.conta_meta_trader!r}>"

# índice parcial (opcional; só mantenha se você realmente cria via SQL também)
Index(
    "contas_chave_do_token_uidx",
    Conta.chave_do_token,
    unique=True,
    postgresql_where=Conta.chave_do_token.isnot(None),
)
