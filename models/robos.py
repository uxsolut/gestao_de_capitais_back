# models/robo.py
from datetime import datetime

from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, LargeBinary
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY

from database import Base


class Robo(Base):
    __tablename__ = "robos"
    __table_args__ = {"schema": "gestor_capitais"}

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(Text, nullable=False)

    # DB: timestamp without time zone NOT NULL (sem default no DB)
    # ORM: garante valor no insert
    criado_em = Column(DateTime, nullable=False, default=datetime.utcnow)

    # DB: text[] (nullable)
    performance = Column(ARRAY(Text), nullable=True)

    # FK para ativos.id no mesmo schema
    id_ativo = Column(Integer, ForeignKey("gestor_capitais.ativos.id"), nullable=True)

    # DB: bytea (nullable)
    arquivo_robo = Column(LargeBinary, nullable=True)

    # ----------------- RELACIONAMENTOS -----------------

    # ativo (FK local -> ativos.id) — pareado com Ativo.robos (back_populates)
    ativo = relationship(
        "Ativo",
        back_populates="robos",
        foreign_keys=[id_ativo],
    )

    # logs.id_robo -> robos.id  (ambos em gestor_capitais)
    logs = relationship(
        "Log",
        back_populates="robo",
        primaryjoin="Robo.id == foreign(Log.id_robo)",
        foreign_keys="Log.id_robo",
        passive_deletes=True,
    )

    # robos_do_user.id_robo -> robos.id
    robos_do_user = relationship(
        "RoboDoUser",
        back_populates="robo",
        primaryjoin="Robo.id == foreign(RoboDoUser.id_robo)",
        foreign_keys="RoboDoUser.id_robo",
        passive_deletes=True,
    )

    # Se você usa relatorios/requisicoes, os FKs estão definidos no outro lado.
    relatorios = relationship("Relatorio", back_populates="robo", cascade="all, delete-orphan")
    requisicoes = relationship("Requisicao", back_populates="robo", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Robo id={self.id} nome={self.nome!r}>"
