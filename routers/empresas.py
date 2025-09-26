# routers/empresas.py
# -*- coding: utf-8 -*-
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Path
from sqlalchemy.orm import Session

from auth.dependencies import get_db, get_current_user
from models.users import User
from models.empresas import Empresa
from schemas.empresas import EmpresaOut, EmpresaCreate, EmpresaUpdate

router = APIRouter(prefix="/empresas", tags=["Empresas"])


# ============================ GET (listar) ============================
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


# ============================ GET (por id) ============================
@router.get(
    "/{id}",
    response_model=EmpresaOut,
    status_code=status.HTTP_200_OK,
    summary="Obter empresa por ID (protegido por JWT)",
)
def obter_empresa(
    id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp = db.query(Empresa).get(id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return emp


# ============================ POST (criar) ============================
@router.post(
    "/",
    response_model=EmpresaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Criar empresa (protegido por JWT)",
)
def criar_empresa(
    payload: EmpresaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cria um registro em `global.empresas`.

    Campos obrigatórios (NOT NULL no banco):
    - `nome`
    - `descricao`

    Opcional:
    - `ramo_de_atividade`
    """
    emp = Empresa(
        nome=payload.nome.strip(),
        descricao=payload.descricao.strip(),
        ramo_de_atividade=(payload.ramo_de_atividade or None),
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


# ============================ PUT (editar) ============================
@router.put(
    "/{id}",
    response_model=EmpresaOut,
    status_code=status.HTTP_200_OK,
    summary="Editar empresa (protegido por JWT)",
)
def editar_empresa(
    id: int = Path(..., gt=0),
    payload: EmpresaUpdate = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp = db.query(Empresa).get(id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")

    # Atualizações condicionais
    if payload.nome is not None:
        emp.nome = payload.nome.strip()
    if payload.descricao is not None:
        emp.descricao = payload.descricao.strip()
    if payload.ramo_de_atividade is not None:
        emp.ramo_de_atividade = payload.ramo_de_atividade or None

    db.commit()
    db.refresh(emp)
    return emp


# ============================ DELETE (apagar) ============================
@router.delete(
    "/{id}",
    status_code=status.HTTP_200_OK,
    summary="Excluir empresa (protegido por JWT)",
)
def excluir_empresa(
    id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp = db.query(Empresa).get(id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")

    db.delete(emp)
    db.commit()
    return {"ok": True, "id": id}
