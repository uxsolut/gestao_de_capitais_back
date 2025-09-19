# models/relatorios.py
from sqlalchemy import Column, Integer, ForeignKey, Date, DateTime, Numeric, Float, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from database import Base

# ENUM já existente no Postgres (em gestor_capitais)
tipo_mercado_enum = PGEnum(
    name="tipo_de_mercado",
    schema="gestor_capitais",
    create_type=False,
)

class Relatorio(Base):
    __tablename__ = "relatorios"
    __table_args__ = {"schema": "gestor_capitais"}  # <- schema correto

    id = Column(Integer, primary_key=True, index=True)

    resultado_do_dia = Column(Float, nullable=False)

    # users está no schema GLOBAL
    id_user = Column(Integer, ForeignKey("global.users.id"), nullable=False)

    data_relatorio = Column(Date, server_default=func.current_date())
    criado_em      = Column(DateTime, server_default=func.now())

    preco_fechamento = Column(Numeric, nullable=True)
    data_cotacao     = Column(Date, nullable=True)

    # Tabelas no MESMO schema gestor_capitais
    id_robo  = Column(Integer, ForeignKey("gestor_capitais.robos.id"),  nullable=True)
    id_ativo = Column(Integer, ForeignKey("gestor_capitais.ativos.id"), nullable=True)

    # enum existente
    tipo_mercado = Column(tipo_mercado_enum, nullable=True)

    # ---------------- RELACIONAMENTOS ----------------
    robo = relationship(
        "Robo",
        back_populates="relatorios",
        primaryjoin="Relatorio.id_robo == foreign(Robo.id)",
        foreign_keys=[id_robo],
    )

    user = relationship(
        "User",
        back_populates="relatorios",
        primaryjoin="Relatorio.id_user == foreign(User.id)",
        foreign_keys=[id_user],
    )

    # Ativo sem back_populates: relacionamento simples
    ativo = relationship(
        "Ativo",
        primaryjoin="Relatorio.id_ativo == foreign(Ativo.id)",
        foreign_keys=[id_ativo],
    )

    def __repr__(self):
        return f"<Relatorio id={self.id} resultado_do_dia={self.resultado_do_dia} data_relatorio={self.data_relatorio}>"

# Índices
Index("ix_relatorios_user_data", Relatorio.id_user, Relatorio.data_relatorio)
Index("ix_relatorios_tipo_mercado_data", Relatorio.tipo_mercado, Relatorio.data_relatorio)
