# models/robos_do_user.py
from sqlalchemy import Column, Integer, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class RoboDoUser(Base):
    __tablename__ = "robos_do_user"
    __table_args__ = {"schema": "gestor_capitais"}

    id = Column(Integer, primary_key=True, index=True)

    id_user     = Column(Integer, ForeignKey("gestor_capitais.users.id", ondelete="CASCADE"), nullable=False)
    id_robo     = Column(Integer, ForeignKey("gestor_capitais.robos.id", ondelete="CASCADE"), nullable=False)
    id_carteira = Column(Integer, ForeignKey("gestor_capitais.carteiras.id", ondelete="SET NULL"), nullable=True)
    id_conta    = Column(Integer, ForeignKey("gestor_capitais.contas.id", ondelete="SET NULL"), nullable=True)
    id_ordem    = Column(Integer, ForeignKey("gestor_capitais.ordens.id", ondelete="SET NULL"), nullable=True)

    # REMOVIDO: id_aplicacao (tabela deletada)
    # id_aplicacao = Column(Integer, ForeignKey("gestor_capitais.aplicacao.id", ondelete="SET NULL"), nullable=True)

    ligado         = Column(Boolean, default=False)
    ativo          = Column(Boolean, default=False)
    tem_requisicao = Column(Boolean, default=False)

    # RELACIONAMENTOS
    user     = relationship("User", back_populates="robos_do_user")
    robo     = relationship("Robo", back_populates="robos_do_user")
    carteira = relationship("Carteira", back_populates="robos_do_user")
    conta    = relationship("Conta", back_populates="robos_do_user")

    # REMOVIDO: relação com Aplicacao
    # aplicacao = relationship("Aplicacao", back_populates="robos_do_user")

    logs = relationship("Log", back_populates="robo_user", cascade="all, delete-orphan")

    # 1-1 opcional para última ordem + 1-N para histórico
    ordem  = relationship("Ordem", foreign_keys=[id_ordem])
    ordens = relationship("Ordem", back_populates="robo_user", foreign_keys="Ordem.id_robo_user")

    def __repr__(self):
        return f"<RobosDoUser(id={self.id}, id_user={self.id_user}, id_robo={self.id_robo}, ligado={self.ligado}, ativo={self.ativo})>"
