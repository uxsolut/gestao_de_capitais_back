# routers/whatsapp_simples.py
# -*- coding: utf-8 -*-

import os
import base64
from typing import Optional

import httpx
from fastapi import (
    APIRouter,
    Form,
    File,
    UploadFile,
    HTTPException,
)

router = APIRouter(
    prefix="/whatsapp",
    tags=["whatsapp"],
)

# Configurações da Z-API vindas do .env
ZAPI_BASE_URL = os.getenv("ZAPI_BASE_URL", "https://api.z-api.io")
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")


def _check_zapi_config():
    """
    Garante que as variáveis de ambiente necessárias estão preenchidas.
    Se quiser outros nomes, é só trocar aqui e no .env.
    """
    missing = []
    if not ZAPI_INSTANCE_ID:
        missing.append("ZAPI_INSTANCE_ID")
    if not ZAPI_TOKEN:
        missing.append("ZAPI_TOKEN")
    if not ZAPI_CLIENT_TOKEN:
        missing.append("ZAPI_CLIENT_TOKEN")

    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Configuração da Z-API incompleta. "
                   f"Faltando variáveis de ambiente: {', '.join(missing)}",
        )


async def _send_text(phone: str, message: str) -> dict:
    """
    Envia texto simples usando o endpoint /send-text da Z-API.
    Docs: /send-text
    """
    _check_zapi_config()

    url = f"{ZAPI_BASE_URL}/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {
        "phone": phone,
        "message": message,
    }

    headers = {
        "Client-Token": ZAPI_CLIENT_TOKEN,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code >= 400:
        try:
            error_data = resp.json()
        except Exception:
            error_data = {"raw": resp.text}

        raise HTTPException(
            status_code=resp.status_code,
            detail={
                "message": "Erro ao enviar texto pela Z-API",
                "zapi_response": error_data,
            },
        )

    return resp.json()


async def _send_image_base64(phone: str, image_file: UploadFile, caption: Optional[str] = None) -> dict:
    """
    Envia imagem em Base64 usando /send-image da Z-API.
    Docs: /send-image
    """
    _check_zapi_config()

    # Garante que é imagem
    if not image_file.content_type or not image_file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de arquivo não suportado para imagem: {image_file.content_type}. "
                   f"Envie um arquivo de imagem (jpg, png, etc.).",
        )

    # Lê o arquivo e converte para Base64
    file_bytes = await image_file.read()
    b64 = base64.b64encode(file_bytes).decode("utf-8")

    # Formato que a Z-API espera para Base64: data:image/png;base64,...
    image_b64 = f"data:{image_file.content_type};base64,{b64}"

    url = f"{ZAPI_BASE_URL}/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-image"
    payload = {
        "phone": phone,
        "image": image_b64,
    }

    if caption:
        payload["caption"] = caption

    headers = {
        "Client-Token": ZAPI_CLIENT_TOKEN,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code >= 400:
        try:
            error_data = resp.json()
        except Exception:
            error_data = {"raw": resp.text}

        raise HTTPException(
            status_code=resp.status_code,
            detail={
                "message": "Erro ao enviar imagem pela Z-API",
                "zapi_response": error_data,
            },
        )

    return resp.json()


@router.post("/enviar", summary="Endpoint genérico para enviar mensagem via Z-API (texto/imagem)")
async def enviar_whatsapp(
    phone: str = Form(..., description="Número no formato 5511999999999, somente dígitos"),
    message: Optional[str] = Form(
        None,
        description="Mensagem de texto. Opcional se estiver enviando apenas imagem."
    ),
    media: Optional[UploadFile] = File(
        None,
        description="Arquivo de imagem opcional. Se enviado junto com 'message', vira legenda."
    ),
):
    """
    Endpoint genérico para envio de mensagens via Z-API.

    Regras:
    - Se tiver APENAS 'message' -> envia texto simples (/send-text)
    - Se tiver 'media' + 'message' -> envia imagem com legenda (/send-image)
    - Se tiver APENAS 'media' -> envia só a imagem (/send-image)
    """

    if not message and not media:
        raise HTTPException(
            status_code=400,
            detail="Informe pelo menos 'message' (texto) ou 'media' (arquivo de imagem).",
        )

    # Caso 1: só texto
    if message and not media:
        zapi_response = await _send_text(phone=phone, message=message)
        return {
            "status": "ok",
            "tipo_envio": "texto",
            "phone": phone,
            "message": message,
            "zapi_response": zapi_response,
        }

    # Caso 2 e 3: tem media (com ou sem texto)
    if media:
        zapi_response = await _send_image_base64(phone=phone, image_file=media, caption=message)
        tipo = "imagem+legenda" if message else "imagem"
        return {
            "status": "ok",
            "tipo_envio": tipo,
            "phone": phone,
            "message": message,
            "arquivo_nome": media.filename,
            "content_type": media.content_type,
            "zapi_response": zapi_response,
        }
