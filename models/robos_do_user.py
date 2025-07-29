from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class RobosDoUser(Base):
    __tablename__ = "robos_do_user"

    id = Column(Integer, primary_key=True, index=True)
    
    id_user = Column(Integer, ForeignKey("users.id"), nullable=False)
    id_robo = Column(Integer, ForeignKey("robos.id"), nullable=False)
    id_conta = Column(Integer, ForeignKey("contas.id"), nullable=False)

    esta_ativo = Column(Boolean, default=True)
    nome_personalizado = Column(String, nullable=True)

    # Auditoria
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    criado_por = Column(Integer, nullable=True)
    atualizado_por = Column(Integer, nullable=True)

    # Relacionamentos
    user = relationship("User", back_populates="robos_do_user")
    robo = relationship("Robo", back_populates="robos_do_user")
    conta = relationship("Conta", back_populates="robos_do_user")
    ordens = relationship("Ordem", back_populates="robo_user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<RobosDoUser(id={self.id}, id_user={self.id_user}, id_robo={self.id_robo}, ativo={self.esta_ativo})>"
