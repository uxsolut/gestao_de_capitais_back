# routers/email.py
import os
import base64
from typing import Optional

from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    status,
    UploadFile,
    File,
    Form,
)
import httpx

router = APIRouter(
    prefix="/email",        # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<< ADICIONADO
    tags=["email"],
)


def _get_env_var(name: str) -> str:
    """Helper pra pegar env var e dar erro decente se estiver faltando."""
    value = os.getenv(name)
    if not value:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Variável de ambiente {name} não configurada no servidor.",
        )
    return value


@router.post(
    "/enviar",              # << mantém apenas o /enviar
    summary="Enviar e-mail via SendGrid (texto + imagem opcional)",
)
async def enviar_email(
    # Header de segurança, igual ao do WhatsApp, mas para e-mail
    x_email_secret: str = Header(..., alias="X-Email-Secret"),
    # Dados do formulário
    to: str = Form(..., description="E-mail de destino (ex: usuario@dominio.com)"),
    subject: str = Form(..., description="Assunto do e-mail"),
    message: str = Form(..., description="Mensagem em HTML ou texto puro"),
    image: Optional[UploadFile] = File(
        None,
        description="Imagem opcional para enviar como anexo",
    ),
):
    """
    Endpoint genérico para enviar e-mail via SendGrid.

    - Protegido por header `X-Email-Secret`
    - Envia texto (HTML ou texto puro)
    - Pode anexar uma imagem opcional
    """

    # 1) Valida segredo do header
    expected_secret = _get_env_var("EMAIL_SECRET")
    if x_email_secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Segredo inválido no header X-Email-Secret.",
        )

    # 2) Pega API Key do SendGrid
    sendgrid_api_key = _get_env_var("SENDGRID_API_KEY")

    # 3) Monta payload do SendGrid
    from_email = "contato@pinacle.com.br"
    from_name = "Pinacle"

    payload = {
        "personalizations": [
            {
                "to": [{"email": to}],
                "subject": subject,
            }
        ],
        "from": {
            "email": from_email,
            "name": from_name,
        },
        "content": [
            {
                "type": "text/html",
                "value": message,
            }
        ],
    }

    # 4) Se tiver imagem, adiciona como anexo
    if image is not None:
        file_bytes = await image.read()
        encoded = base64.b64encode(file_bytes).decode("utf-8")

        attachment = {
            "content": encoded,
            "type": image.content_type or "application/octet-stream",
            "filename": image.filename or "anexo",
            "disposition": "attachment",
        }

        payload["attachments"] = [attachment]

    # 5) Chama a API do SendGrid
    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {sendgrid_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload, headers=headers)

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Falha ao enviar e-mail via SendGrid.",
                "sendgrid_status": response.status_code,
                "sendgrid_body": response.text,
            },
        )

    return {"success": True, "detail": "E-mail enviado com sucesso."}
