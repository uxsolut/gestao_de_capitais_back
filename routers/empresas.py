# routers/empresas.py
# -*- coding: utf-8 -*-
from fastapi import APIRouter
from typing import List
from sqlalchemy import text
from database import engine
from schemas.empresas import EmpresaOut

router = APIRouter(prefix="/empresas", tags=["Empresas"])

@router.get("", response_model=List[EmpresaOut], summary="Listar Empresas")
def listar_empresas():
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT id, nome, descricao, ramo_de_atividade
                FROM global.empresas
                ORDER BY id
            """)
        ).mappings().all()
    return [EmpresaOut(**dict(r)) for r in rows]
