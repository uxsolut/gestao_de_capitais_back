# models/analises.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    SmallInteger,
    Text,
    ForeignKey,
    CheckConstraint,
    func,
)
from sqlalchemy.orm import relationship

from database import Base

class Analise(Base):
    __tablename__ = "analises"
    __table_args__ = (
        CheckConstraint("voto >= 1 AND voto <= 10", name="analises_voto_check"),
        {"schema": "tetra_music"},
    )

    id = Column(Integer, primary_key=True, index=True)  # identity INTEGER
    id_user = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        name="id_user",
    )
    telefone = Column(Text, nullable=False)
    voto = Column(SmallInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="analises", passive_deletes=True)

    def __repr__(self) -> str:
        return f"<Analise id={self.id} id_user={self.id_user} voto={self.voto}>"
