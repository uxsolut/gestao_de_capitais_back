from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum

# ---- Enum Python (mantenha os mesmos valores do enum do Postgres) ----
class TipoLogEnum(str, enum.Enum):
    INFO = "INFO"
    ERRO = "ERRO"
    AVISO = "AVISO"
    # acrescente se o seu enum do banco tiver mais

# IMPORTA A CLASSE para evitar resolução por string
from models.aplicacao import Aplicacao
# (opcional) pode manter os demais como string; se quiser, também pode importar RoboDoUser/Robo/Conta/User

class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    data_hora = Column(DateTime, nullable=False, default=func.now())

    # Aponta para o tipo ENUM já existente no Postgres (tipologenum)
    tipo = Column(
        Enum(
            TipoLogEnum,
            name="tipologenum",      # <- nome do tipo no banco
            native_enum=True,
            create_type=False,       # <- não recriar o tipo
            validate_strings=True,
        ),
        nullable=False,
    )

    conteudo = Column(Text, nullable=False)

    id_usuario = Column(Integer, ForeignKey("users.id"))
    id_aplicacao = Column(Integer, ForeignKey("aplicacao.id"))
    id_robo = Column(Integer, ForeignKey("robos.id"))
    id_robo_user = Column(Integer, ForeignKey("robos_do_user.id"))
    id_conta = Column(Integer, ForeignKey("contas.id"))

    criado_em = Column(DateTime, nullable=False, default=func.now())

    # ---- Relacionamentos ----
    usuario = relationship("User", back_populates="logs")
    aplicacao = relationship(Aplicacao, back_populates="logs")  # <- usa a CLASSE
    robo = relationship("Robo", back_populates="logs")
    robo_user = relationship("RoboDoUser", back_populates="logs")
    conta = relationship("Conta", back_populates="logs")

    def __repr__(self):
        return f"<Log id={self.id} tipo={self.tipo} id_aplicacao={self.id_aplicacao} id_robo_user={self.id_robo_user}>"
