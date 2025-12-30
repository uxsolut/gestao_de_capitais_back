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
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    payload = f"{code}:{settings.SECRET_KEY}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def access_code_expires_at(ttl_minutes: int = 10) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)


def jwt_exp_minutes() -> int:
    return 720  # 12h (pode ajustar depois)


def create_contacts_jwt(sub: str, extra: dict) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=jwt_exp_minutes())
    payload = {"sub": sub, "iat": int(now.timestamp()), "exp": int(exp.timestamp()), **extra}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALG)


def send_access_code_whatsapp(phone: str, code: str) -> None:
    """
    Aqui é onde você liga no seu envio real.
    Como você já tem um router de WhatsApp funcionando no próprio projeto,
    o caminho mais limpo é chamar a função/serviço interno que ele já usa.

    Como eu não tenho esse arquivo aqui agora, deixo o envio como "print".
    Assim suas APIs já funcionam 100% e depois a gente troca por 2 linhas.
    """
    print(f"[WHATS] Enviar código {code} para {phone}")
