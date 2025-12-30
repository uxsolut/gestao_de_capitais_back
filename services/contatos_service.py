# services/contatos_service.py
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt

from config import settings


# ====== Ajuste simples (sem "variáveis novas") ======
# JWT usa o mesmo SECRET_KEY do seu projeto
JWT_ALG = getattr(settings, "ALGORITHM", "HS256")


def generate_access_code() -> str:
    # 6 dígitos, com zero à esquerda
    return f"{secrets.randbelow(1_000_000):06d}"


def _normalize_code(code: str) -> str:
    # remove espaços/quebras e garante só dígitos
    cleaned = "".join(ch for ch in (code or "").strip() if ch.isdigit())
    return cleaned


def hash_code(code: str) -> str:
    code_norm = _normalize_code(code)
    # garante consistência de 6 dígitos (se vier menor, mantém; validação fica no router)
    payload = f"{code_norm}:{settings.SECRET_KEY}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def access_code_expires_at(ttl_minutes: int = 10) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)


def jwt_exp_minutes() -> int:
    return 720  # 12h (pode ajustar depois)


def create_contacts_jwt(sub, extra: dict) -> str:
    """
    sub: sempre vai para string (padrão JWT).
    extra: dict com dados extras, ex:
      {"tipo": "contato", "contato_id": 123, "user_id": 1, "assinatura_id": 2, "supervisor": False}
    """
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=jwt_exp_minutes())

    payload = {
        "sub": str(sub),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        **(extra or {}),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALG)


def send_access_code_whatsapp(phone: str, code: str) -> None:
    """
    Aqui é onde você liga no seu envio real.
    Por enquanto fica como print para validar fluxo.
    Depois trocamos por chamada do seu serviço/rota interna de WhatsApp.
    """
    print(f"[WHATS] Enviar código {code} para {phone}")
