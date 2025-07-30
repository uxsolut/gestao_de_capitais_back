from sqlalchemy import Column, Integer, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class RobosDoUser(Base):
    __tablename__ = "robos_do_user"

    id = Column(Integer, primary_key=True, index=True)

    id_user = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    id_robo = Column(Integer, ForeignKey("robos.id", ondelete="CASCADE"), nullable=False)
    id_carteira = Column(Integer, ForeignKey("carteiras.id", ondelete="SET NULL"), nullable=True)
    id_conta = Column(Integer, ForeignKey("contas.id", ondelete="SET NULL"), nullable=True)
    id_ordem = Column(Integer, ForeignKey("ordens.id", ondelete="SET NULL"), nullable=True)
    id_aplicacao = Column(Integer, ForeignKey("aplicacao.id", ondelete="SET NULL"), nullable=True)

    ligado = Column(Boolean, default=False)
    ativo = Column(Boolean, default=False)
    tem_requisicao = Column(Boolean, default=False)

    # RELACIONAMENTOS
    user = relationship("User", back_populates="robos_do_user")
    robo = relationship("Robo", back_populates="robos_do_user")
    carteira = relationship("Carteira", back_populates="robos_do_user")
    conta = relationship("Conta", back_populates="robos_do_user")
    aplicacao = relationship("Aplicacao", back_populates="robos_do_user")

    ordem = relationship("Ordem", foreign_keys=[id_ordem])
    ordens = relationship("Ordem", back_populates="robo_user", foreign_keys="[Ordem.id_robo_user]")

    def __repr__(self):
        return f"<RobosDoUser(id={self.id}, id_user={self.id_user}, id_robo={self.id_robo}, ligado={self.ligado}, ativo={self.ativo})>"
