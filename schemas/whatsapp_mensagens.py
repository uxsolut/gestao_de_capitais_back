# schemas/whatsapp_mensagens.py
# -*- coding: utf-8 -*-

from datetime import datetime
from typing import Optional, Any, Dict

from pydantic import BaseModel


class WhatsAppMensagemBase(BaseModel):
    instance_id: Optional[str] = None
    message_id: Optional[str] = None
    phone: str
    sender_name: Optional[str] = None
    chat_name: Optional[str] = None
    texto: Optional[str] = None
    status: Optional[str] = None
    from_me: bool = False
    momment: Optional[datetime] = None


class WhatsAppMensagemResponse(WhatsAppMensagemBase):
    """
    Usado no GET /whatsapp/mensagens
    (inclui raw_payload completo).
    """
    id: int
    raw_payload: Dict[str, Any]
    created_at: datetime

    class Config:
        orm_mode = True


class WhatsAppMensagemDetalheResponse(WhatsAppMensagemResponse):
    """
    Usado no GET /whatsapp/mensagens/{id}.
    Por enquanto é igual ao de lista, mas separado se
    você quiser customizar depois.
    """
    pass
