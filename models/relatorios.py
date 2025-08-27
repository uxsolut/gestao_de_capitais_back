from sqlalchemy import Column, Integer, ForeignKey, Date, DateTime, Numeric, Float, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from database import Base

# Reaproveita o ENUM já existente no PostgreSQL (não criar/alterar tipo)
tipo_mercado_enum = PGEnum(name='tipo_de_mercado', create_type=False)

class Relatorio(Base):
    __tablename__ = "relatorios"

    id = Column(Integer, primary_key=True, index=True)
    resultado_do_dia = Column(Float, nullable=False)
    id_user = Column(Integer, ForeignKey("users.id"), nullable=False)

    data_relatorio = Column(Date, server_default=func.current_date())
    criado_em = Column(DateTime, server_default=func.now())

    preco_fechamento = Column(Numeric, nullable=True)
    data_cotacao = Column(Date, nullable=True)

    id_robo = Column(Integer, ForeignKey("robos.id"), nullable=True)
    id_ativo = Column(Integer, ForeignKey("ativos.id"), nullable=True)

    # NOVO CAMPO (enum tipo_de_mercado)
    tipo_mercado = Column(tipo_mercado_enum, nullable=True)

    # Relacionamentos (ajuste conforme seus outros models)
    robo = relationship("Robo", back_populates="relatorios")
    user = relationship("User", back_populates="relatorios")
    # Se o model Ativo NÃO possui .relatorios, mantenha assim (sem back_populates):
    ativo = relationship("Ativo", foreign_keys=[id_ativo])
    # Se Ativo tiver .relatorios, você pode usar:
    # ativo = relationship("Ativo", back_populates="relatorios")

    def __repr__(self):
        return f"<Relatorio id={self.id} resultado_do_dia={self.resultado_do_dia} data_relatorio={self.data_relatorio}>"

# Índices úteis
Index("ix_relatorios_user_data", Relatorio.id_user, Relatorio.data_relatorio)
Index("ix_relatorios_tipo_mercado_data", Relatorio.tipo_mercado, Relatorio.data_relatorio)
