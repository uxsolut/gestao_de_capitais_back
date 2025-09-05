# routers/users.py
# -*- coding: utf-8 -*-
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.users import User  # usa SAEnum(UserRole, name="user_role") no modelo
from schemas.users import User as UserSchema, UserCreate, UserLogin
from auth.dependencies import get_current_user

# >>> use sempre o módulo único de auth <<<
from auth.auth import gerar_hash_senha, verificar_senha, criar_token_acesso

router = APIRouter(prefix="/users", tags=["Users"])


def _enum_value(v) -> Optional[str]:
    """Converte Enum -> str para respostas JSON; se já for str/None, retorna como está."""
    if v is None:
        return None
    return getattr(v, "value", v)


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
        # item.tipo_de_user é Enum (schemas) -> SQLAlchemy aceita Enum ou string.
        # Se quiser ser explícito, converta para .value:
        tipo_de_user=_enum_value(item.tipo_de_user),
    )
    db.add(novo_user)
    db.commit()
    db.refresh(novo_user)
    return novo_user  # Pydantic (response_model) serializa o Enum do modelo automaticamente


# ---------- LOGIN ----------
@router.post("/login", response_model=dict)
def login_user(item: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == item.email).first()
    if not user or not verificar_senha(item.senha, user.senha):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
        )

    # cria o JWT com a MESMA SECRET_KEY/ALGORITHM do verificador
    access_token = criar_token_acesso(sub=str(user.id))

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "nome": user.nome,
            "email": user.email,
            "cpf": user.cpf,
            # garante string no JSON mesmo que seja Enum na sessão
            "tipo_de_user": _enum_value(user.tipo_de_user),
        },
    }


# ---------- LISTAR USUÁRIOS ----------
@router.get("/", response_model=List[UserSchema])
def listar_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # usa HTTPBearer
):
    return db.query(User).all()
