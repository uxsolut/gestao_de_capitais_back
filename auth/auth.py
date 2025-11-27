# auth/auth.py
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import jwt, JWTError, ExpiredSignatureError
from passlib.context import CryptContext
from fastapi import HTTPException, status
import os

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY não definida (verifique /etc/app.env e o systemd).")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# =========================
# HASH / VERIFICAÇÃO DE SENHA
# =========================

def verificar_senha(senha_pura: str, senha_hash: str) -> bool:
    return pwd_context.verify(senha_pura, senha_hash)


def gerar_hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)


# =========================
# CRIAÇÃO DE TOKENS
# =========================

def _build_payload_base(
    sub: str,
    minutes: int | None,
    token_type: str,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Monta o payload base padronizado:
    - sub: id do usuário (string)
    - iat: emitido em (timestamp)
    - exp: expiração (timestamp)
    - type: "access" ou "2fa" (ou outro se precisar no futuro)
    """
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=minutes or ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": str(sub),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": token_type,
    }

    if extra_claims:
        payload.update(extra_claims)

    return payload


def criar_token_acesso(
    sub: str,
    minutes: int | None = None,
    token_type: str = "access",
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Cria um JWT genérico, mas por padrão do tipo "access".
    - token_type="access" -> token normal de login
    - token_type="2fa"    -> token temporário usado no fluxo de 2FA
    """
    payload = _build_payload_base(sub, minutes, token_type, extra_claims)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def criar_token_2fa(sub: str, two_factor_id: int, minutes: int = 10) -> str:
    """
    Helper específico para criar token temporário de 2FA.
    Esse token NÃO deve ser aceito como token de acesso normal.
    """
    extra = {"two_factor_id": two_factor_id}
    return criar_token_acesso(sub=sub, minutes=minutes, token_type="2fa", extra_claims=extra)


# =========================
# VERIFICAÇÃO DE TOKENS
# =========================

def verificar_token(token: str) -> int:
    """
    Verifica um token de ACESSO (login normal).
    - Rejeita tokens cujo type != "access" (ex.: "2fa").
    - Retorna o id do usuário (int).
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Por compatibilidade, se "type" não existir, consideramos "access"
        token_type = payload.get("type", "access")
        if token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token não é de acesso.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token sem ID de usuário",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return int(sub)

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verificar_token_2fa(token: str) -> tuple[int, int]:
    """
    Verifica um token TEMPORÁRIO de 2FA.
    - Garante que type == "2fa"
    - Retorna (user_id, two_factor_id)
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        token_type = payload.get("type")
        if token_type != "2fa":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token não é de 2FA.",
            )

        sub = payload.get("sub")
        two_factor_id = payload.get("two_factor_id")

        if not sub or two_factor_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token de 2FA incompleto.",
            )

        return int(sub), int(two_factor_id)

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de 2FA expirado.",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de 2FA inválido.",
        )
