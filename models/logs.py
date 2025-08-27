from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


# Enum do tipo_log (você pode ajustar os valores conforme o ENUM real do banco)
class TipoLogEnum(str, enum.Enum):
    INFO = "INFO"
    ERRO = "ERRO"
    AVISO = "AVISO"
    # Adicione aqui os valores reais do enum "tipo_log" se forem diferentes


class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    data_hora = Column(DateTime, nullable=False, default=func.now())
    tipo = Column(Enum(TipoLogEnum), nullable=False)
    conteudo = Column(Text, nullable=False)

    id_usuario = Column(Integer, ForeignKey("users.id"))
    id_aplicacao = Column(Integer, ForeignKey("aplicacao.id"))
    id_robo = Column(Integer, ForeignKey("robos.id"))
    id_robo_user = Column(Integer, ForeignKey("robos_do_user.id"))
    id_conta = Column(Integer, ForeignKey("contas.id"))

    criado_em = Column(DateTime, nullable=False, default=func.now())

    # Relacionamentos
    usuario = relationship("User", back_populates="logs")
    aplicacao = relationship("Aplicacao", back_populates="logs")
    robo = relationship("Robo", back_populates="logs")
    robo_user = relationship("RoboDoUser", back_populates="logs")
    conta = relationship("Conta", back_populates="logs")
