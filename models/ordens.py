# models/ordens.py
from enum import Enum as PyEnum

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

from database import Base

# --- Enums do Postgres ---------------------------------------------------------
class OrdemStatus(PyEnum):
    INICIALIZADO = "Inicializado"
    CONSUMIDO    = "Consumido"
    # adicione outros se existirem no tipo ordem_status

OrdemStatusDB = PGEnum(
    OrdemStatus,
    name="ordem_status",
    values_callable=lambda e: [m.value for m in e],
    create_type=False,
)

tipo_de_acao_enum = PGEnum(
    "BUY", "SELL", "CLOSE", "PATCH",
    name="tipo_de_acao",
    create_type=False,
)

# --- Modelo --------------------------------------------------------------------
class Ordem(Base):
    __tablename__ = "ordens"

    id = Column(Integer, primary_key=True, index=True)

    id_robo_user = Column(Integer, ForeignKey("robos_do_user.id", ondelete="SET NULL"), nullable=True)
    id_user      = Column(Integer, ForeignKey("users.id",        ondelete="SET NULL"), nullable=True)

    numero_unico      = Column(Text,    nullable=True)
    conta_meta_trader = Column(String,  nullable=True)

    criado_em = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    status = Column(OrdemStatusDB, nullable=False, server_default=OrdemStatus.INICIALIZADO.value)

    id_tipo_ordem = Column(Integer, ForeignKey("tipo_de_ordem.id", ondelete="RESTRICT"), nullable=True)
    tipo          = Column(tipo_de_acao_enum, nullable=True)

    # Relacionamentos
    robo_user  = relationship("RoboDoUser", back_populates="ordens", foreign_keys=[id_robo_user])
    user       = relationship("User",       back_populates="ordens")
    tipo_ordem = relationship("TipoDeOrdem", foreign_keys=[id_tipo_ordem])

    def __repr__(self) -> str:
        return f"<Ordem id={self.id} tipo={self.tipo} status={self.status} numero_unico={self.numero_unico!r}>"

# Índices conforme o banco
Index("idx_ordens_id_tipo_ordem", Ordem.id_tipo_ordem)
