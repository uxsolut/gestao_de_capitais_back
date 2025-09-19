# models/analises.py
from sqlalchemy import Column, Integer, SmallInteger, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from database import Base

class Analise(Base):
    __tablename__ = "analises"
    __table_args__ = {"schema": "tetra_music"}

    id = Column(Integer, primary_key=True, index=True)
    # >>> aponta explicitamente para o schema correto da tabela users
    id_user = Column(Integer, ForeignKey("global.users.id", ondelete="CASCADE"), nullable=True, index=True)
    telefone = Column(Text, nullable=True)
    voto = Column(SmallInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())

    user = relationship("User", lazy="joined", backref="analises")
