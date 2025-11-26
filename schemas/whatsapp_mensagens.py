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
    raw_payload: Dict[str, Any]


class WhatsAppMensagemResponse(WhatsAppMensagemBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True
