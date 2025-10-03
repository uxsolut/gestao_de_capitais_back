# routers/desvio_rota_front.py
# -*- coding: utf-8 -*-
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from database import engine

# 🔐 Proteção igual às outras APIs (ajuste o caminho se necessário)
from auth.dependencies import get_current_user
from models.users import User

router = APIRouter(prefix="/desvio_rota_front", tags=["Desvio de Rota Front"])

# Tipos válidos (devem bater com o ENUM do banco: tipo_de_pagina_enum)
TipoPagina = Literal["comum", "nao_tem", "login"]
TIPOS_VALIDOS = {"comum", "nao_tem", "login"}


class DesvioRotaFrontCreate(BaseModel):
    id_aplicacao: int
    tipo_de_pagina: TipoPagina


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Cria um desvio de rota/front para uma aplicação",
)
def create_desvio_rota_front(
    payload: DesvioRotaFrontCreate,
    current_user: User = Depends(get_current_user),
):
    """
    Insere um registro em global.desvio_rota_front com:
      - id_aplicacao: int (FK para global.aplicacoes.id)
      - tipo_de_pagina: 'comum' | 'nao_tem' | 'login'
    Retorna o registro criado (id, id_aplicacao, tipo_de_pagina).
    """
    if payload.tipo_de_pagina not in TIPOS_VALIDOS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"tipo_de_pagina inválido. Use um de: {sorted(TIPOS_VALIDOS)}",
        )

    sql = text("""
        INSERT INTO global.desvio_rota_front (id_aplicacao, tipo_de_pagina)
        VALUES (:id_aplicacao, :tipo_de_pagina)
        RETURNING id, id_aplicacao, tipo_de_pagina
    """)

    try:
        with engine.begin() as conn:
            row = conn.execute(
                sql,
                {
                    "id_aplicacao": payload.id_aplicacao,
                    "tipo_de_pagina": payload.tipo_de_pagina,
                },
            ).mappings().first()

        if not row:
            # Não era para acontecer, mas é uma proteção
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Falha ao criar o desvio de rota.",
            )

        return {
            "id": row["id"],
            "id_aplicacao": row["id_aplicacao"],
            "tipo_de_pagina": row["tipo_de_pagina"],
        }

    except IntegrityError as e:
        # Erros comuns: FK inválida, violação de unique (se você tiver adicionado),
        # ou enum inválido (se passar direto ao DB).
        msg = "Violação de integridade (verifique id_aplicacao e tipo_de_pagina)."
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao acessar o banco de dados.",
        ) from e
