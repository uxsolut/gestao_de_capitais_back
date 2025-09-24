# routers/empresas.py
# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from sqlalchemy import text
from database import engine
from schemas.empresas import EmpresaOut

router = APIRouter(prefix="/empresas", tags=["Empresas"])

@router.get("/", response_model=List[EmpresaOut])
def listar_empresas(
    q: Optional[str] = Query(None, description="Filtro por nome/ramo (ILIKE)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    sql = """
        SELECT id, nome, descricao, ramo_de_atividade
        FROM global.empresas
    """
    params = {}
    if q:
        sql += " WHERE nome ILIKE :q OR ramo_de_atividade ILIKE :q"
        params["q"] = f"%{q}%"
    sql += " ORDER BY id LIMIT :limit OFFSET :offset"
    params.update({"limit": limit, "offset": offset})

    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [EmpresaOut(**dict(r)) for r in rows]

@router.get("/{empresa_id}", response_model=EmpresaOut)
def obter_empresa(empresa_id: int):
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT id, nome, descricao, ramo_de_atividade
                FROM global.empresas
                WHERE id = :id
            """),
            {"id": empresa_id},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return EmpresaOut(**dict(row))
