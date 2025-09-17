# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database import get_db
from models.analises import Analise
from models.users import User  # para o tipo do current_user
from schemas.analises import AnaliseCreate, AnaliseOut

# Se você já tem autenticação, aproveite:
from auth.dependencies import get_current_user  # ajuste o caminho se for diferente

router = APIRouter(prefix="/analises", tags=["Análises"])


@router.post(
    "/",
    response_model=AnaliseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Criar uma análise (voto 1..10)",
)
def criar_analise(
    payload: AnaliseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cria uma nova análise para o usuário logado (ou para um usuário específico, se admin).
    - `voto`: inteiro entre **1 e 10**
    - `telefone`: texto obrigatório
    - `id_user`: opcional — se não for enviado, usa o `current_user.id`.
    """
    # Se não veio id_user no payload, usa o do usuário autenticado
    id_user = payload.id_user or current_user.id

    # (Opcional) Se quiser restringir para que somente admin crie para terceiros:
    if payload.id_user and payload.id_user != current_user.id:
        # Exemplo de verificação simples de admin
        is_admin = getattr(current_user, "is_admin", False)
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas administradores podem criar análises para outros usuários.",
            )

    nova = Analise(
        id_user=id_user,
        telefone=payload.telefone,
        voto=payload.voto,
    )

    db.add(nova)
    try:
        db.commit()
        db.refresh(nova)
    except IntegrityError as e:
        db.rollback()
        # Pode ser violação de FK (users.id inexistente) ou outra constraint
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não foi possível criar a análise (verifique o usuário/voto).",
        ) from e

    return nova
