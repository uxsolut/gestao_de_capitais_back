# routers/robos_do_user.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth.dependencies import get_db, get_current_user
from models.users import User
from models.robos_do_user import RoboDoUser  # seu modelo SQLAlchemy
from schemas.robos_do_user import RoboDoUserCreate, RoboDoUserOut

router = APIRouter(prefix="/robos_do_user", tags=["Robôs do Usuário"])


@router.post(
    "/",
    response_model=RoboDoUserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Vincular robô ao usuário/conta (id_user vem do JWT)"
)
def criar_robo_do_user(
    payload: RoboDoUserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cria (ou atualiza) o vínculo do usuário autenticado com um robô.
    - `id_user` é inferido do JWT (current_user.id).
    - Se `ligado=True`, é **recomendado** informar `id_conta` para o pipeline de processamento.
    - Faz *upsert* do par (id_user, id_robo, id_conta) para evitar duplicidades.
    """
    # Regras de negócio úteis: se ligar o robô, peça id_conta
    if payload.ligado and payload.id_conta is None:
        raise HTTPException(
            status_code=422,
            detail="Para ligar o robô (ligado=true), informe id_conta."
        )

    # Procura vínculo existente do mesmo user + robo + (conta igual/NULL)
    q = db.query(RoboDoUser).filter(
        RoboDoUser.id_user == current_user.id,
        RoboDoUser.id_robo == payload.id_robo,
    )
    if payload.id_conta is None:
        q = q.filter(RoboDoUser.id_conta.is_(None))
    else:
        q = q.filter(RoboDoUser.id_conta == payload.id_conta)

    existente: Optional[RoboDoUser] = q.first()

    if existente:
        # Atualiza campos editáveis
        existente.id_carteira   = payload.id_carteira
        existente.id_conta      = payload.id_conta
        existente.id_ordem      = payload.id_ordem
        existente.id_aplicacao  = payload.id_aplicacao

        if payload.ligado is not None:
            existente.ligado = payload.ligado
        if payload.ativo is not None:
            existente.ativo = payload.ativo
        if payload.tem_requisicao is not None:
            existente.tem_requisicao = payload.tem_requisicao

        db.commit()
        db.refresh(existente)
        return existente

    # Cria novo
    novo = RoboDoUser(
        id_user=current_user.id,
        id_robo=payload.id_robo,
        id_carteira=payload.id_carteira,
        id_conta=payload.id_conta,
        id_ordem=payload.id_ordem,
        id_aplicacao=payload.id_aplicacao,
        ligado=payload.ligado or False,
        ativo=payload.ativo or False,
        tem_requisicao=payload.tem_requisicao or False,
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo
