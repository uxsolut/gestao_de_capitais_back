# routers/whatsapp_simples.py
# -*- coding: utf-8 -*-

import os
import base64
import logging
from datetime import datetime, timezone
from typing import Optional, List

import httpx
from fastapi import (
    APIRouter,
    Form,
    File,
    UploadFile,
    HTTPException,
    Request,
    Header,
    Depends,
)
from sqlalchemy.orm import Session

from database import get_db
from models.whatsapp_mensagens import WhatsAppMensagem
from schemas.whatsapp_mensagens import WhatsAppMensagemResponse

router = APIRouter(
    prefix="/whatsapp",
    tags=["whatsapp"],
)

logger = logging.getLogger("whatsapp_zapi")

# ================================
# VARIÁVEIS DE AMBIENTE / CONFIG
# ================================
# De acordo com o SEU .env:
# ZAPI_INSTANCE_ID
# ZAPI_INSTANCE_TOKEN
# ZAPI_CLIENT_TOKEN
# (ZAPI_BASE_URL é opcional, com padrão)

ZAPI_BASE_URL = os.getenv("ZAPI_BASE_URL", "https://api.z-api.io")
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_INSTANCE_TOKEN = os.getenv("ZAPI_INSTANCE_TOKEN")  # usa o que você já tem
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")

# 🔐 CHAVE SECRETA PARA USAR SUAS APIS (enviar + gets)
# se quiser mudar, coloque WHATS_API_SECRET no .env
WHATS_API_SECRET = os.getenv(
    "WHATS_API_SECRET",
    "y83!T7DtxgzfXKYB2hYkjkGJPjzev85W4E9RTZCjvc&ksE%x%o",
)


def _check_zapi_config():
    """
    Garante que as variáveis de ambiente necessárias estão preenchidas.
    """
    missing = []
    if not ZAPI_INSTANCE_ID:
        missing.append("ZAPI_INSTANCE_ID")
    if not ZAPI_INSTANCE_TOKEN:
        missing.append("ZAPI_INSTANCE_TOKEN")
    if not ZAPI_CLIENT_TOKEN:
        missing.append("ZAPI_CLIENT_TOKEN")

    if missing:
        raise HTTPException(
            status_code=500,
            detail=(
                "Configuração da Z-API incompleta. "
                f"Faltando variáveis de ambiente: {', '.join(missing)}"
            ),
        )


# ==========================================================
# AUTENTICAÇÃO POR CHAVE SECRETA
# ==========================================================

async def validar_chave_secreta(
    x_whats_secret: str = Header(
        ...,
        alias="X-Whats-Secret",
        description="Chave secreta para usar a API de WhatsApp",
    ),
):
    """
    Valida a chave secreta enviada no header `X-Whats-Secret`.
    Qualquer backend que tiver essa chave pode usar /whatsapp/enviar
    e os endpoints protegidos (como GET de mensagens).
    """
    if not WHATS_API_SECRET:
        raise HTTPException(
            status_code=500,
            detail="WHATS_API_SECRET não configurada no servidor.",
        )

    if x_whats_secret != WHATS_API_SECRET:
        raise HTTPException(
            status_code=401,
            detail="Não autorizado: chave secreta inválida.",
        )


# ==========================================================
# FUNÇÕES PARA ENVIAR MENSAGENS VIA Z-API
# ==========================================================

async def _send_text(phone: str, message: str) -> dict:
    """
    Envia texto simples usando o endpoint /send-text da Z-API.
    Ajuste a URL se sua doc usar outro caminho.
    """
    _check_zapi_config()

    url = (
        f"{ZAPI_BASE_URL}/instances/"
        f"{ZAPI_INSTANCE_ID}/token/{ZAPI_INSTANCE_TOKEN}/send-text"
    )

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


async def _send_image_base64(
    phone: str,
    image_file: UploadFile,
    caption: Optional[str] = None,
) -> dict:
    """
    Envia imagem em Base64 usando /send-image da Z-API.
    Ajuste campos conforme a doc oficial (image/fileBase64/etc).
    """
    _check_zapi_config()

    if not image_file.content_type or not image_file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Tipo de arquivo não suportado para imagem: {image_file.content_type}. "
                f"Envie um arquivo de imagem (jpg, png, etc.)."
            ),
        )

    file_bytes = await image_file.read()
    b64 = base64.b64encode(file_bytes).decode("utf-8")

    # Exemplo genérico usando data URL; ajuste conforme a doc da Z-API
    image_b64 = f"data:{image_file.content_type};base64,{b64}"

    url = (
        f"{ZAPI_BASE_URL}/instances/"
        f"{ZAPI_INSTANCE_ID}/token/{ZAPI_INSTANCE_TOKEN}/send-image"
    )

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


# ==========================================================
# ENDPOINT PARA ENVIAR (PROTEGIDO POR CHAVE SECRETA)
# ==========================================================

@router.post(
    "/enviar",
    summary="Endpoint genérico para enviar mensagem via Z-API (texto/imagem)",
    dependencies=[Depends(validar_chave_secreta)],
)
async def enviar_whatsapp(
    phone: str = Form(..., description="Número no formato 5511999999999, somente dígitos"),
    message: Optional[str] = Form(
        None,
        description="Mensagem de texto. Opcional se estiver enviando apenas imagem.",
    ),
    media: Optional[UploadFile] = File(
        None,
        description="Arquivo de imagem opcional. Se enviado junto com 'message', vira legenda.",
    ),
):
    """
    Regras:
    - Se tiver APENAS 'message' -> envia texto simples (/send-text)
    - Se tiver 'media' + 'message' -> envia imagem com legenda (/send-image)
    - Se tiver APENAS 'media' -> envia só a imagem (/send-image)

    ⚠️ Protegido por X-Whats-Secret.
    """

    if not message and not media:
        raise HTTPException(
            status_code=400,
            detail="Informe pelo menos 'message' (texto) ou 'media' (arquivo de imagem).",
        )

    # Só texto
    if message and not media:
        zapi_response = await _send_text(phone=phone, message=message)
        return {
            "status": "ok",
            "tipo_envio": "texto",
            "phone": phone,
            "message": message,
            "zapi_response": zapi_response,
        }

    # Tem arquivo (com ou sem legenda)
    if media:
        zapi_response = await _send_image_base64(
            phone=phone,
            image_file=media,
            caption=message,
        )
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


# ==========================================================
# WEBHOOK - RECEBER DA Z-API E SALVAR NA TABELA
# ==========================================================

@router.post(
    "/webhook",
    summary="Webhook para receber eventos/mensagens da Z-API",
)
async def whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Endpoint que a Z-API vai chamar quando chegar mensagem nova
    (URL configurada no painel da Z-API em 'Ao receber').

    Aqui ele:
    - lê o JSON enviado
    - grava no log
    - salva os campos principais em global.whatsapp_mensagens
    - guarda o raw_payload completo em JSONB
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    logger.info("Webhook Z-API recebido: %s", body)

    # Campos principais
    instance_id = body.get("instanceId")
    message_id = body.get("messageId")
    phone = body.get("phone") or body.get("chatId")
    sender_name = body.get("senderName") or body.get("chatName")
    chat_name = body.get("chatName")
    status = body.get("status")
    from_me = bool(body.get("fromMe", False))

    texto = None
    text_block = body.get("text")
    if isinstance(text_block, dict):
        texto = text_block.get("message")

    momment = None
    momment_raw = body.get("momment")
    if isinstance(momment_raw, (int, float)):
        # Z-API manda em milissegundos
        momment = datetime.fromtimestamp(momment_raw / 1000.0, tz=timezone.utc)

    # Cria registro
    mensagem = WhatsAppMensagem(
        instance_id=instance_id,
        message_id=message_id,
        phone=phone or "",
        sender_name=sender_name,
        chat_name=chat_name,
        texto=texto,
        status=status,
        from_me=from_me,
        momment=momment,
        raw_payload=body,
    )

    db.add(mensagem)
    db.commit()
    db.refresh(mensagem)

    return {"status": "ok", "recebido": True, "id": mensagem.id}


# ==========================================================
# GET DE MENSAGENS (PROTEGIDO POR CHAVE SECRETA)
# ==========================================================

@router.get(
    "/mensagens",
    response_model=List[WhatsAppMensagemResponse],
    summary="Lista mensagens recebidas/salvas (filtrando por telefone opcionalmente)",
    dependencies=[Depends(validar_chave_secreta)],
)
async def listar_mensagens(
    phone: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    Lista mensagens da tabela global.whatsapp_mensagens.

    - Se `phone` for informado, filtra pelo número.
    - Limit padrão = 50 (mais recentes primeiro).

    ⚠️ Protegido por X-Whats-Secret.
    """
    query = db.query(WhatsAppMensagem)

    if phone:
        query = query.filter(WhatsAppMensagem.phone == phone)

    mensagens = (
        query.order_by(WhatsAppMensagem.momment.desc().nullslast())
        .limit(limit)
        .all()
    )

    return mensagens
