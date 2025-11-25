# schemas/email_envio.py
# -*- coding: utf-8 -*-
import enum
from typing import Optional

from pydantic import BaseModel


class TipoConteudoEmailEnum(str, enum.Enum):
    TEXTO = "texto"
    HTML = "html"


class EmailEnvioCreate(BaseModel):
    id_user: int
    tipo_user: str
    assunto: str
    mensagem: str
    tipo_conteudo: TipoConteudoEmailEnum = TipoConteudoEmailEnum.TEXTO


class EmailEnvioResponse(BaseModel):
    id: int
    id_user: int
    tipo_user: str
    email_destino: str
    assunto: str
    mensagem: str
    tipo_conteudo: TipoConteudoEmailEnum
    status: str
    erro: Optional[str] = None

    class Config:
        orm_mode = True
