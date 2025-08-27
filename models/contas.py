# models/contas.py
from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, Text, DateTime, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Conta(Base):
    __tablename__ = "contas"

    id = Column(Integer, primary_key=True, index=True)
    # no print do \d não há unique em conta_meta_trader, então não marcamos unique=True
    conta_meta_trader = Column(String, nullable=True)

    id_corretora = Column(Integer, ForeignKey("corretoras.id", ondelete="SET NULL"), nullable=True)
    id_carteira  = Column(Integer, ForeignKey("carteiras.id", ondelete="SET NULL"),  nullable=True)

    # no schema não está NOT NULL -> deixamos nullable=True
    nome = Column(Text, nullable=True)

    margem_total      = Column(Numeric, nullable=True)
    margem_disponivel = Column(Numeric, nullable=True)

    jwt_atual  = Column(Text, nullable=True)

    # default vem do banco: CURRENT_TIMESTAMP
    updated_at = Column(DateTime(timezone=False),
                        server_default=func.current_timestamp(),
                        onupdate=func.current_timestamp(),
                        nullable=True)

    # NOVO: token agora pertence à conta
    chave_do_token = Column(Text, nullable=True)

    # Relacionamentos
    corretora     = relationship("Corretora", back_populates="contas")
    carteira      = relationship("Carteira",  back_populates="contas")
    robos_do_user = relationship("RoboDoUser", back_populates="conta")

    logs = relationship(
        "Log",
        back_populates="conta",
        cascade="all, delete-orphan",
        lazy="selectin",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Conta id={self.id} nome={self.nome!r} conta_meta_trader={self.conta_meta_trader!r}>"

# Índice único parcial (opcional declarar aqui; já existe via SQL)
Index(
    "contas_chave_do_token_uidx",
    Conta.chave_do_token,
    unique=True,
    postgresql_where=Conta.chave_do_token.isnot(None),
)
