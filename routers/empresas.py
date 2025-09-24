# routers/empresas.py
# -*- coding: utf-8 -*-
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from auth.dependencies import get_db, get_current_user
from models.users import User
from models.empresas import Empresa
from schemas.empresas import EmpresaOut

router = APIRouter(prefix="/empresas", tags=["Empresas"])

@router.get(
    "/",
    response_model=List[EmpresaOut],
    status_code=status.HTTP_200_OK,
    summary="Listar empresas (protegido por JWT)",
)
def listar_empresas(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retorna todas as empresas.
    - Protegido por JWT (usa `get_current_user`).
    - Ordena por `id` ascendente.
    """
    return db.query(Empresa).order_by(Empresa.id.asc()).all()
