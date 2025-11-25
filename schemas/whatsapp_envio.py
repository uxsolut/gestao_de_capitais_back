# schemas/whatsapp_envivo.py
# -*- coding: utf-8 -*-
import enum
from typing import Optional

from pydantic import BaseModel


class TipoMensagemEnum(str, enum.Enum):
    TEXTO = "texto"
    IMAGEM = "imagem"


class WhatsAppEnvioBase(BaseModel):
    id_user: int
    tipo_user: str
    tipo_mensagem: TipoMensagemEnum
    mensagem: str


class WhatsAppEnvioResponse(BaseModel):
    id: int
    id_user: int
    tipo_user: str
    tipo_mensagem: TipoMensagemEnum
    telefone_destino: str
    mensagem: str
    imagem: Optional[str] = None
    status: str

    class Config:
        from_attributes = True  # Pydantic v2 (ou orm_mode=True no v1)
