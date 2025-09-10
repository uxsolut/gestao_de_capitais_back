from sqlalchemy import Column, Integer, Text, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum

# ---------------- Enums Python ----------------
class TipoFrontEndEnum(str, enum.Enum):
    flutter = "flutter"
    web = "web"
    mobile = "mobile"
    # adicione aqui os valores que EXISTEM no enum do banco, se houver mais

class FrontBackEnum(str, enum.Enum):
    frontend = "frontend"
    backend = "backend"
    fullstack = "fullstack"
    # idem: mantenha em sincronia com o enum do banco

# Importa a CLASSE para evitar resolução por string
from models.aplicacao import Aplicacao

class TipoDeAplicacao(Base):
    __tablename__ = "tipo_de_aplicacao"

    id = Column(Integer, primary_key=True, index=True)

    # IMPORTANTES: use o nome exato do tipo do Postgres e evite recriação
    tipo_front_end = Column(
        Enum(
            TipoFrontEndEnum,
            name="tipofrontendenum",      # nome do tipo no Postgres
            native_enum=True,
            create_type=False,            # NÃO criar novamente
            validate_strings=True,
        ),
        nullable=True,
    )

    tipo_aplicacao = Column(
        Enum(
            FrontBackEnum,
            name="frontbackenum",         # nome do tipo no Postgres
            native_enum=True,
            create_type=False,
            validate_strings=True,
        ),
        nullable=True,
    )

    descricao = Column(Text, nullable=True)
    criado_em = Column(DateTime, nullable=False, default=func.now())

    # 1-N com Aplicacao (usa a CLASSE, não string)
    aplicacoes = relationship(Aplicacao, back_populates="tipo_aplicacao")

    def __repr__(self) -> str:
        return f"<TipoDeAplicacao id={self.id} tipo_front_end={self.tipo_front_end} tipo_aplicacao={self.tipo_aplicacao}>"
