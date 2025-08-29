# auth/auth.py
from datetime import datetime, timedelta, timezone
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

def verificar_senha(senha_pura: str, senha_hash: str) -> bool:
    return pwd_context.verify(senha_pura, senha_hash)

def gerar_hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)

def criar_token_acesso(sub: str, minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=minutes or ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(sub), "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verificar_token(token: str) -> int:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Token sem ID de usuário",
                                headers={"WWW-Authenticate": "Bearer"})
        return int(sub)
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado",
                            headers={"WWW-Authenticate": "Bearer"})
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido",
                            headers={"WWW-Authenticate": "Bearer"})
