# routers/users.py
# -*- coding: utf-8 -*-
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import secrets
import hashlib
import os

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from database import get_db
from models.users import User
from models.two_factor_tokens import TwoFactorToken
from schemas.users import User as UserSchema, UserCreate, UserLogin
from auth.dependencies import get_current_user

# >>> use sempre o módulo único de auth <<<
from auth.auth import (
    gerar_hash_senha,
    verificar_senha,
    criar_token_acesso,
    verificar_token,  # <<< NOVO (para validar cookie/session/check)
    SECRET_KEY,
    ALGORITHM,
)

from routers.whatsapp_simples import _send_text

router = APIRouter(prefix="/users", tags=["Users"])

# =============================
# COOKIE JWT (ServerMonitor)
# =============================
COOKIE_NAME = os.getenv("SM_COOKIE_NAME", "sm_token")
COOKIE_PATH = os.getenv("SM_COOKIE_PATH", "/servermonitor")
COOKIE_SAMESITE = os.getenv("SM_COOKIE_SAMESITE", "lax")  # lax|strict|none
COOKIE_MAX_AGE_SECONDS = int(os.getenv("SM_COOKIE_MAX_AGE", str(60 * 60 * 24 * 7)))  # 7 dias

# Em produção HTTPS => True. Se quiser controlar por env:
COOKIE_SECURE = os.getenv("SM_COOKIE_SECURE", "true").lower() == "true"


def _enum_value(v) -> Optional[str]:
    """Converte Enum -> str para respostas JSON; se já for str/None, retorna como está."""
    if v is None:
        return None
    return getattr(v, "value", v)


def _set_auth_cookie(resp: Response, token: str) -> None:
    """
    Grava o JWT final em cookie HttpOnly para o Nginx poder proteger /servermonitor
    ANTES de carregar a página.
    """
    resp.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=COOKIE_MAX_AGE_SECONDS,
    )


def _clear_auth_cookie(resp: Response) -> None:
    resp.delete_cookie(key=COOKIE_NAME, path=COOKIE_PATH)


# =============================
# SCHEMAS PARA LOGIN 2FA
# =============================

class UserLogin2FA(BaseModel):
    email: str
    senha: str


class UserLogin2FAStep2(BaseModel):
    code: str
    two_factor_token: str


# ---------- CRIAR USUÁRIO ----------
@router.post("/", response_model=UserSchema)
def criar_user(item: UserCreate, db: Session = Depends(get_db)):
    # E-mail único
    if db.query(User).filter(User.email == item.email).first():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado.")

    # CPF único (se fornecido)
    if item.cpf and db.query(User).filter(User.cpf == item.cpf).first():
        raise HTTPException(status_code=400, detail="CPF já cadastrado.")

    hashed_password = gerar_hash_senha(item.senha)

    novo_user = User(
        nome=item.nome,
        email=item.email,
        senha=hashed_password,
        cpf=item.cpf,
        tipo_de_user=_enum_value(item.tipo_de_user),
    )
    db.add(novo_user)
    db.commit()
    db.refresh(novo_user)
    return novo_user


# ---------- LOGIN SIMPLES (mantém JSON e também seta cookie HttpOnly) ----------
@router.post("/login", response_model=dict)
def login_user(item: UserLogin, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == item.email).first()
    if not user or not verificar_senha(item.senha, user.senha):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
        )

    # cria o JWT (type="access" no seu auth/auth.py)
    access_token = criar_token_acesso(sub=str(user.id))

    # >>> NOVO: seta cookie para proteger /servermonitor
    _set_auth_cookie(response, access_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "nome": user.nome,
            "email": user.email,
            "cpf": user.cpf,
            "tipo_de_user": _enum_value(user.tipo_de_user),
        },
    }


# ==========================================================
# LOGIN EM DUAS ETAPAS (2FA VIA WHATSAPP)
# ==========================================================

def _gerar_codigo_otp(tamanho: int = 6) -> str:
    """Gera um código numérico aleatório, ex.: '123456'."""
    return "".join(secrets.choice("0123456789") for _ in range(tamanho))


def _hash_codigo(code: str) -> str:
    """Hash simples do código para não salvar em texto puro."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _criar_token_2fa_jwt(user_id: int, two_factor_id: int, minutos: int = 10) -> str:
    """
    Cria um JWT TEMPORÁRIO apenas para a etapa de 2FA.
    Não é o token de acesso da aplicação.
    """
    agora = datetime.now(timezone.utc)
    exp = agora + timedelta(minutes=minutos)
    payload = {
        "sub": str(user_id),
        "two_factor_id": int(two_factor_id),
        "type": "2fa",
        "iat": int(agora.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/login-2fa-step1", response_model=dict)
async def login_2fa_step1(item: UserLogin2FA, db: Session = Depends(get_db)):
    """
    1ª etapa do login 2FA:
    - verifica email/senha
    - gera código de 6 dígitos
    - grava em global.two_factor_tokens
    - envia o código via WhatsApp usando o telefone do usuário
    - retorna um token temporário de 2FA (two_factor_token)
    """
    user = db.query(User).filter(User.email == item.email).first()
    if not user or not verificar_senha(item.senha, user.senha):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
        )

    if not user.telefone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário não possui telefone cadastrado para 2FA.",
        )

    codigo = _gerar_codigo_otp()
    agora = datetime.now(timezone.utc)
    expires_at = agora + timedelta(minutes=5)

    token_2fa = TwoFactorToken(
        user_id=user.id,
        code_hash=_hash_codigo(codigo),
        expires_at=expires_at,
        used=False,
        attempts=0,
    )
    db.add(token_2fa)
    db.commit()
    db.refresh(token_2fa)

    mensagem = f"Seu código de verificação é: {codigo}"
    await _send_text(phone=user.telefone, message=mensagem)

    two_factor_token = _criar_token_2fa_jwt(
        user_id=user.id,
        two_factor_id=token_2fa.id,
        minutos=10,
    )

    return {
        "status": "OTP_SENT",
        "message": "Enviamos um código de verificação para o seu WhatsApp.",
        "two_factor_token": two_factor_token,
        "user": {
            "id": user.id,
            "nome": user.nome,
            "email": user.email,
            "tipo_de_user": _enum_value(user.tipo_de_user),
        },
    }


@router.post("/login-2fa-step2", response_model=dict)
def login_2fa_step2(item: UserLogin2FAStep2, response: Response, db: Session = Depends(get_db)):
    """
    2ª etapa do login 2FA:
    - recebe o code (digitado) e o two_factor_token
    - valida token temporário
    - valida código (tentativas, expiração, uso)
    - se ok, gera o mesmo JWT final do login normal e retorna
    """
    # 1) Decodificar o token temporário
    try:
        payload = jwt.decode(item.two_factor_token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de verificação inválido ou expirado.",
        )

    if payload.get("type") != "2fa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token informado não é de verificação em duas etapas.",
        )

    sub = payload.get("sub")
    two_factor_id = payload.get("two_factor_id")

    if not sub or two_factor_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de verificação incompleto.",
        )

    try:
        user_id = int(sub)
        two_factor_id = int(two_factor_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de verificação inválido.",
        )

    token_db = (
        db.query(TwoFactorToken)
        .filter(
            TwoFactorToken.id == two_factor_id,
            TwoFactorToken.user_id == user_id,
        )
        .first()
    )

    if not token_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código de verificação não encontrado.",
        )

    agora = datetime.now(timezone.utc)

    if token_db.used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Este código já foi utilizado.")

    if agora > token_db.expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código expirado.")

    if token_db.attempts >= 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Número máximo de tentativas excedido.")

    token_db.attempts += 1

    if token_db.code_hash == _hash_codigo(item.code):
        token_db.used = True
        db.add(token_db)
        db.commit()
    else:
        db.add(token_db)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código inválido.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário não encontrado.",
        )

    access_token = criar_token_acesso(sub=str(user.id))

    # >>> NOVO: seta cookie para proteger /servermonitor
    _set_auth_cookie(response, access_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "nome": user.nome,
            "email": user.email,
            "cpf": user.cpf,
            "tipo_de_user": _enum_value(user.tipo_de_user),
        },
    }


# =============================
# CHECK DE SESSÃO (para Nginx auth_request)
# =============================
@router.get("/session/check", response_model=dict)
def session_check(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Sem sessão.")

    # Usa seu verificador: garante type=access, exp ok, etc.
    verificar_token(token)

    return {"ok": True}


@router.post("/logout", response_model=dict)
def logout(response: Response) -> dict:
    _clear_auth_cookie(response)
    return {"ok": True}


# ---------- LISTAR USUÁRIOS ----------
@router.get("/", response_model=List[UserSchema])
def listar_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # usa HTTPBearer
):
    return db.query(User).all()
