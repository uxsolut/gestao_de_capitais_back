# models/logs.py
from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum

class TipoLogEnum(str, enum.Enum):
    INFO = "INFO"
    ERRO = "ERRO"
    AVISO = "AVISO"

class Log(Base):
    __tablename__ = "logs"
    __table_args__ = {"schema": "gestor_capitais"}

    id = Column(Integer, primary_key=True, index=True)
    data_hora = Column(DateTime, nullable=False, default=func.now())

    tipo = Column(
        Enum(
            TipoLogEnum,
            name="tipologenum",
            native_enum=True,
            create_type=False,
            validate_strings=True,
        ),
        nullable=False,
    )

    conteudo = Column(Text, nullable=False)

    # ✅ corrigido: users está no schema GLOBAL
    id_usuario   = Column(Integer, ForeignKey("global.users.id"))
    id_robo      = Column(Integer, ForeignKey("gestor_capitais.robos.id"))
    id_robo_user = Column(Integer, ForeignKey("gestor_capitais.robos_do_user.id"))
    id_conta     = Column(Integer, ForeignKey("gestor_capitais.contas.id"))

    criado_em = Column(DateTime, nullable=False, default=func.now())

    # Relacionamentos
    usuario   = relationship("User", back_populates="logs")
    robo      = relationship("Robo", back_populates="logs")
    robo_user = relationship("RoboDoUser", back_populates="logs")
    conta     = relationship("Conta", back_populates="logs")

    def __repr__(self):
        return f"<Log id={self.id} tipo={self.tipo} id_robo_user={self.id_robo_user}>"
