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

from database import get_db
from models.users import User
from models.two_factor_tokens import TwoFactorToken
from schemas.users import User as UserSchema
from auth.dependencies import get_current_user
from auth.auth import criar_token_acesso, verificar_token, SECRET_KEY, ALGORITHM
from routers.whatsapp_simples import _send_text
from jose import jwt, JWTError

router = APIRouter(prefix="/users", tags=["Users"])

# =============================
# COOKIE JWT (ServerMonitor)
# =============================
COOKIE_NAME = os.getenv("SM_COOKIE_NAME", "sm_token")
COOKIE_PATH = os.getenv("SM_COOKIE_PATH", "/servermonitor")
COOKIE_SAMESITE = os.getenv("SM_COOKIE_SAMESITE", "lax")
COOKIE_MAX_AGE_SECONDS = int(os.getenv("SM_COOKIE_MAX_AGE", str(60 * 60 * 24 * 7)))
COOKIE_SECURE = os.getenv("SM_COOKIE_SECURE", "true").lower() == "true"


def _enum_value(v) -> Optional[str]:
    """Converte Enum -> str para respostas JSON"""
    if v is None:
        return None
    return getattr(v, "value", v)


def _set_auth_cookie(resp: Response, token: str) -> None:
    """Grava o JWT final em cookie HttpOnly"""
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
    """Remove o cookie de autenticação"""
    resp.delete_cookie(key=COOKIE_NAME, path=COOKIE_PATH)


# =============================
# SCHEMAS
# =============================

class UserLoginPhone(BaseModel):
    """Login por email + telefone"""
    email: str
    telefone: str


class UserLogin2FAStep2(BaseModel):
    """Validação de OTP"""
    code: str
    two_factor_token: str


class UserRegister(BaseModel):
    """Registro de novo usuário"""
    nome: str
    email: str
    telefone: str


# =============================
# FUNÇÕES AUXILIARES
# =============================

def _gerar_codigo_otp(tamanho: int = 6) -> str:
    """Gera um código numérico aleatório"""
    return "".join(secrets.choice("0123456789") for _ in range(tamanho))


def _hash_codigo(code: str) -> str:
    """Hash do código para não salvar em texto puro"""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _criar_token_2fa_jwt(user_id: int, two_factor_id: int, minutos: int = 10) -> str:
    """Cria JWT temporário para 2FA"""
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


# =============================
# ENDPOINTS
# =============================

@router.post("/login-phone-step1", response_model=dict)
async def login_phone_step1(item: UserLoginPhone, db: Session = Depends(get_db)):
    """
    Etapa 1: Email + Telefone → OTP
    
    - Verifica se usuário existe com email + telefone
    - Se não existe: retorna 404 (frontend vai para cadastro)
    - Se existe: gera OTP, envia via WhatsApp, retorna two_factor_token
    """
    # 1) Verificar se email + telefone existem juntos
    user = db.query(User).filter(
        User.email == item.email,
        User.telefone == item.telefone
    ).first()
    
    if not user:
        # 2) Se não encontrou, verificar conflitos
        email_exists = db.query(User).filter(User.email == item.email).first()
        phone_exists = db.query(User).filter(User.telefone == item.telefone).first()
        
        if email_exists and phone_exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email e telefone já existem com usuários diferentes.",
            )
        elif email_exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email já existe com outro telefone.",
            )
        elif phone_exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Telefone já existe com outro email.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado. Crie uma conta.",
            )
    
    # 3) Usuário existe - gerar OTP
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
    
    # 4) Enviar OTP via WhatsApp
    mensagem = f"Seu código de verificação é: {codigo}\n\nEste código expira em 5 minutos."
    try:
        await _send_text(phone=user.telefone, message=mensagem)
    except Exception as e:
        print(f"Erro ao enviar WhatsApp: {e}")
    
    # 5) Gerar token temporário de 2FA
    two_factor_token = _criar_token_2fa_jwt(
        user_id=user.id,
        two_factor_id=token_2fa.id,
        minutos=10,
    )
    
    return {
        "two_factor_token": two_factor_token,
        "user": {
            "id": user.id,
            "nome": user.nome,
            "email": user.email,
            "telefone": user.telefone,
            "tipo_de_user": _enum_value(user.tipo_de_user),
        },
    }


@router.post("/login-phone-step2", response_model=dict)
def login_phone_step2(item: UserLogin2FAStep2, response: Response, db: Session = Depends(get_db)):
    """
    Etapa 2: Validar OTP → JWT
    
    - Recebe código OTP + two_factor_token
    - Valida código
    - Retorna JWT de acesso
    """
    # 1) Decodificar token temporário
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
            detail="Token informado não é de verificação.",
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
    
    # 2) Buscar token 2FA no banco
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
    
    # 3) Validações
    if token_db.used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este código já foi utilizado.",
        )
    
    if agora > token_db.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código expirado.",
        )
    
    if token_db.attempts >= 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Número máximo de tentativas excedido.",
        )
    
    token_db.attempts += 1
    
    # 4) Validar código
    if token_db.code_hash == _hash_codigo(item.code):
        token_db.used = True
        db.add(token_db)
        db.commit()
    else:
        db.add(token_db)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido.",
        )
    
    # 5) Buscar usuário
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário não encontrado.",
        )
    
    # 6) Gerar JWT de acesso
    access_token = criar_token_acesso(sub=str(user.id))
    _set_auth_cookie(response, access_token)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "nome": user.nome,
            "email": user.email,
            "telefone": user.telefone,
            "tipo_de_user": _enum_value(user.tipo_de_user),
        },
    }


@router.post("/register", response_model=dict)
def register_user(item: UserRegister, db: Session = Depends(get_db)):
    """
    Registrar novo usuário
    
    - Cria novo usuário com nome, email, telefone
    - Valida duplicatas
    """
    # 1) Validar campos
    if not item.nome or len(item.nome) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nome deve ter pelo menos 3 caracteres.",
        )
    
    if not item.email or "@" not in item.email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Email inválido.",
        )
    
    if not item.telefone or len(item.telefone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")) < 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Telefone inválido (mínimo 10 dígitos).",
        )
    
    # 2) Verificar email duplicado
    if db.query(User).filter(User.email == item.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email já existe.",
        )
    
    # 3) Verificar telefone duplicado
    if db.query(User).filter(User.telefone == item.telefone).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Telefone já existe.",
        )
    
    # 4) Criar usuário
    novo_user = User(
        nome=item.nome,
        email=item.email,
        telefone=item.telefone,
        senha="",  # Sem senha
        tipo_de_user="cliente",
    )
    
    db.add(novo_user)
    db.commit()
    db.refresh(novo_user)
    
    return {
        "id": novo_user.id,
        "nome": novo_user.nome,
        "email": novo_user.email,
        "telefone": novo_user.telefone,
        "tipo_de_user": _enum_value(novo_user.tipo_de_user),
    }


@router.get("/session/check", response_model=dict)
def session_check(request: Request) -> dict:
    """Verificar sessão"""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Sem sessão.")

    verificar_token(token)

    return {"ok": True}


@router.post("/logout", response_model=dict)
def logout(response: Response) -> dict:
    """Fazer logout"""
    _clear_auth_cookie(response)
    return {"ok": True}


@router.get("/", response_model=List[UserSchema])
def listar_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Listar usuários"""
    return db.query(User).all()