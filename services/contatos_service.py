# services/contatos_service.py
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import requests
from jose import jwt

from config import settings


JWT_ALG = getattr(settings, "ALGORITHM", "HS256")


def generate_access_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _normalize_code(code: str) -> str:
    cleaned = "".join(ch for ch in (code or "").strip() if ch.isdigit())
    return cleaned


def hash_code(code: str) -> str:
    code_norm = _normalize_code(code)
    payload = f"{code_norm}:{settings.SECRET_KEY}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def access_code_expires_at(ttl_minutes: int = 10) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)


def jwt_exp_minutes() -> int:
    return 720  # 12h


def create_contacts_jwt(sub, extra: dict) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=jwt_exp_minutes())
    payload = {
        "sub": str(sub),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        **(extra or {}),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALG)


def _only_digits(phone: str) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def send_access_code_whatsapp(phone: str, code: str) -> None:
    """
    Envia código via seu endpoint interno /whatsapp/enviar
    - Header: X-Whats-Secret
    - multipart/form-data: phone, message
    """
    secret = getattr(settings, "WHATSAPP_SECRET", None) or getattr(settings, "WHATS_SECRET", None)
    send_url = getattr(settings, "WHATSAPP_SEND_URL", None)

    if not secret:
        raise RuntimeError("WHATSAPP_SECRET não configurado no .env")
    if not send_url:
        raise RuntimeError("WHATSAPP_SEND_URL não configurado no .env")

    phone_digits = _only_digits(phone)
    if not phone_digits:
        raise RuntimeError("Telefone inválido para envio (sem dígitos)")

    message = f"Seu código de acesso é: {code}"

    headers = {"X-Whats-Secret": secret}
    files = {
        "phone": (None, phone_digits),
        "message": (None, message),
        # media é opcional — não enviamos
    }

    try:
        resp = requests.post(send_url, headers=headers, files=files, timeout=20)
    except Exception as e:
        raise RuntimeError(f"Falha ao chamar WhatsApp ({send_url}): {e}") from e

    if resp.status_code >= 400:
        raise RuntimeError(f"WhatsApp retornou {resp.status_code}: {resp.text[:300]}")
