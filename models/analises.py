# models/analises.py
from sqlalchemy import Column, Integer, SmallInteger, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from database import Base  # seu Base = declarative_base()

class Analise(Base):
    __tablename__ = "analises"
    __table_args__ = {"schema": "tetra_music"}  # explicita o schema

    id = Column(Integer, primary_key=True, index=True)
    id_user = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    telefone = Column(Text, nullable=False)
    voto = Column(SmallInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # opcional: relacionamento com User, se você já tiver o modelo
    user = relationship("User", backref="analises", lazy="joined")
