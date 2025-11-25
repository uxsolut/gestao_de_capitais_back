# routers/email.py
# -*- coding: utf-8 -*-
import os
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.users import User
from models.email_envio import EmailEnvio
from schemas.email_envio import (
    EmailEnvioCreate,
    EmailEnvioResponse,
    TipoConteudoEmailEnum,
)

router = APIRouter(
    prefix="/email",
    tags=["Email"],
)

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "no-reply@pinacle.com.br")
SENDGRID_FROM_NAME = os.getenv("SENDGRID_FROM_NAME", "Pinacle")
SENDGRID_ENABLED = bool(SENDGRID_API_KEY)


async def enviar_via_sendgrid(
    email_destino: str,
    assunto: str,
    mensagem: str,
    tipo_conteudo: TipoConteudoEmailEnum,
) -> None:
    """
    Envio REAL via SendGrid (se SENDGRID_API_KEY estiver configurada).
    Lança HTTPException 500 se der erro na API.
    """
    if not SENDGRID_ENABLED:
        # não deveria ser chamado se não tiver key; proteção extra
        raise HTTPException(
            status_code=500,
            detail="SENDGRID_API_KEY não configurada no ambiente.",
        )

    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json",
    }

    content_type = "text/plain" if tipo_conteudo == TipoConteudoEmailEnum.TEXTO else "text/html"

    payload = {
        "personalizations": [
            {"to": [{"email": email_destino}]}
        ],
        "from": {"email": SENDGRID_FROM_EMAIL, "name": SENDGRID_FROM_NAME},
        "subject": assunto,
        "content": [
            {
                "type": content_type,
                "value": mensagem,
            }
        ],
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code not in (200, 202):
        raise HTTPException(
            status_code=500,
            detail=f"Erro SendGrid: status={resp.status_code}, body={resp.text}",
        )


@router.post("/enviar", response_model=EmailEnvioResponse)
async def enviar_email(
    data: EmailEnvioCreate,
    db: Session = Depends(get_db),
):
    """
    Envia (ou simula envio) de e-mail via SendGrid, usando o e-mail do usuário
    (tabela global.users) a partir de id_user.

    - Registra sempre em global.email_envios.
    - Se houver SENDGRID_API_KEY, tenta envio real e marca status=enviado/erro.
    - Se não houver, mantém status=simulado.
    """

    # 1) Buscar usuário
    user = db.query(User).filter(User.id == data.id_user).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"Usuário {data.id_user} não encontrado.")

    if not user.email:
        raise HTTPException(
            status_code=400,
            detail=f"Usuário {data.id_user} não possui e-mail cadastrado.",
        )

    email_destino = user.email

    # 2) Criar registro inicial (simulado)
    envio = EmailEnvio(
        id_user=data.id_user,
        tipo_user=data.tipo_user,
        tipo_conteudo=data.tipo_conteudo.value,
        email_destino=email_destino,
        assunto=data.assunto,
        mensagem=data.mensagem,
        status="simulado",
        created_at=datetime.utcnow(),
    )
    db.add(envio)
    db.commit()
    db.refresh(envio)

    # 3) Se tivermos SENDGRID_API_KEY, tenta envio real
    if SENDGRID_ENABLED:
        try:
            await enviar_via_sendgrid(
                email_destino=email_destino,
                assunto=data.assunto,
                mensagem=data.mensagem,
                tipo_conteudo=data.tipo_conteudo,
            )
            envio.status = "enviado"
            envio.erro = None
        except HTTPException as e:
            envio.status = "erro"
            envio.erro = e.detail if isinstance(e.detail, str) else str(e.detail)
        except Exception as e:
            envio.status = "erro"
            envio.erro = str(e)

        db.add(envio)
        db.commit()
        db.refresh(envio)

    # 4) Retorna o registro
    return envio
