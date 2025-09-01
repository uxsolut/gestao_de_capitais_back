from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from auth.dependencies import get_db, get_current_user
from models import Conta, Corretora, Robo, RoboDoUser, User, Carteira
from schemas.cliente_contas import (
    ContaResponse,
    ContaUpdate,
    CorretoraResponse,
    RoboResponse,
    RoboDoUserResponse,
    RoboDoUserCreate,
    ContaCreate,
)

router = APIRouter(prefix="/cliente", tags=["Cliente - Contas e Robôs"])


# 1. GET /cliente/contas?id_carteira=123
@router.get("/contas", response_model=List[ContaResponse])
def get_contas(
    id_carteira: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verifica se a carteira pertence ao usuário
    carteira = db.query(Carteira).filter(
        Carteira.id == id_carteira,
        Carteira.id_user == user.id
    ).first()

    if not carteira:
        raise HTTPException(status_code=403, detail="Carteira não encontrada ou não pertence ao usuário.")

    contas = (
        db.query(Conta)
        .join(Corretora, Conta.id_corretora == Corretora.id)
        .filter(Conta.id_carteira == id_carteira)
        .with_entities(
            Conta.id,
            Conta.nome,
            Conta.conta_meta_trader,
            Conta.margem_total,
            Conta.margem_disponivel,
            Conta.id_corretora,
            Conta.id_carteira,
            Corretora.nome.label("nome_corretora"),
        )
        .all()
    )

    return contas


# 2. GET /cliente/corretoras
@router.get("/corretoras", response_model=List[CorretoraResponse])
def get_corretoras(db: Session = Depends(get_db)):
    return db.query(Corretora).with_entities(Corretora.id, Corretora.nome).all()


# 3. GET /cliente/robos
@router.get("/robos", response_model=List[RoboResponse])
def get_robos(db: Session = Depends(get_db)):
    return (
        db.query(Robo)
        .with_entities(Robo.id, Robo.nome, Robo.performance)
        .all()
    )


# 4. GET /cliente/robos_do_user
@router.get("/robos_do_user", response_model=List[RoboDoUserResponse])
def get_robos_do_user(
    conta: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = (
        db.query(RoboDoUser)
        .join(Robo, RoboDoUser.id_robo == Robo.id)
        .filter(RoboDoUser.id_user == user.id)
    )

    if conta is not None:
        query = query.filter(RoboDoUser.id_conta == conta)

    robos = query.with_entities(
        RoboDoUser.id,
        RoboDoUser.ligado,
        RoboDoUser.ativo,
        RoboDoUser.tem_requisicao,
        RoboDoUser.id_robo,
        RoboDoUser.id_conta,
        RoboDoUser.id_carteira, 
        Robo.nome.label("nome_robo"),
    ).all()

    return robos


# 5. POST /cliente/contas
@router.post("/contas", response_model=ContaResponse)
def criar_conta(
    conta: ContaCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verifica se a carteira existe e pertence ao usuário logado
    carteira = db.query(Carteira).filter(
        Carteira.id == conta.id_carteira,
        Carteira.id_user == user.id
    ).first()
    if not carteira:
        raise HTTPException(status_code=403, detail="Carteira não encontrada ou não pertence a este usuário.")

    # Corretora é OPCIONAL: só valida se veio informada
    corretora_id: Optional[int] = None
    corretora_nome: Optional[str] = None
    if conta.id_corretora is not None:
        corretora = db.query(Corretora).filter_by(id=conta.id_corretora).first()
        if not corretora:
            raise HTTPException(status_code=404, detail="Corretora não encontrada")
        corretora_id = corretora.id
        corretora_nome = corretora.nome

    nova_conta = Conta(
        nome=conta.nome,
        conta_meta_trader=conta.conta_meta_trader,
        id_corretora=conta.id_corretora,  # pode ser None
        id_carteira=conta.id_carteira,
        margem_total=0.0,
        margem_disponivel=0.0,
    )
    db.add(nova_conta)
    db.commit()
    db.refresh(nova_conta)

    return ContaResponse(
        id=nova_conta.id,
        nome=nova_conta.nome,
        conta_meta_trader=nova_conta.conta_meta_trader,
        margem_total=nova_conta.margem_total,
        margem_disponivel=nova_conta.margem_disponivel,
        id_corretora=corretora_id,
        nome_corretora=corretora_nome,
    )


# 6. POST /cliente/contas/robos_do_user
@router.post("/robos_do_user", response_model=RoboDoUserResponse)
def criar_robo_do_user(
    dados: RoboDoUserCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verifica se a conta pertence à carteira informada e ao usuário
    conta = (
        db.query(Conta)
        .join(Carteira)
        .filter(
            Conta.id == dados.id_conta,
            Conta.id_carteira == dados.id_carteira,
            Carteira.id_user == user.id,
        )
        .first()
    )
    if not conta:
        raise HTTPException(status_code=403, detail="Conta ou carteira inválida.")

    # Verifica se o robô já está vinculado à conta
    ja_existe = (
        db.query(RoboDoUser)
        .filter_by(id_robo=dados.id_robo, id_conta=dados.id_conta)
        .first()
    )
    if ja_existe:
        raise HTTPException(status_code=400, detail="Este robô já está vinculado à conta.")

    novo = RoboDoUser(
        id_user=user.id,
        id_robo=dados.id_robo,
        id_carteira=dados.id_carteira,
        id_conta=dados.id_conta,
        ligado=False,
        ativo=False,
        tem_requisicao=False,
    )

    db.add(novo)
    db.commit()
    db.refresh(novo)

    # Pega nome do robô para resposta
    robo = db.query(Robo).filter_by(id=dados.id_robo).first()

    return RoboDoUserResponse(
      id=novo.id,
      ligado=novo.ligado,
      ativo=novo.ativo,
      tem_requisicao=novo.tem_requisicao,
      id_robo=novo.id_robo,
      id_conta=novo.id_conta,
      id_carteira=novo.id_carteira,
      nome_robo=robo.nome,
    )


# 7. PUT /cliente/contas/{conta_id}
@router.put("/contas/{conta_id}", response_model=ContaResponse)
def atualizar_conta(
    conta_id: int,
    dados: ContaUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conta = (
        db.query(Conta)
        .join(Carteira)
        .filter(
            Conta.id == conta_id,
            Carteira.id == Conta.id_carteira,
            Carteira.id_user == user.id
        )
        .first()
    )
    if not conta:
        raise HTTPException(status_code=403, detail="Conta não encontrada ou não pertence a este usuário.")

    # Verifica se a corretora existe
    corretora = db.query(Corretora).filter_by(id=dados.id_corretora).first()
    if not corretora:
        raise HTTPException(status_code=404, detail="Corretora não encontrada")

    # Atualiza os dados
    conta.nome = dados.nome
    conta.conta_meta_trader = dados.conta_meta_trader
    conta.id_corretora = dados.id_corretora

    db.commit()
    db.refresh(conta)

    return ContaResponse(
        id=conta.id,
        nome=conta.nome,
        conta_meta_trader=conta.conta_meta_trader,
        margem_total=conta.margem_total,
        margem_disponivel=conta.margem_disponivel,
        id_corretora=conta.id_corretora,
        nome_corretora=corretora.nome,
    )


# 8. DELETE /cliente/contas/{conta_id}
@router.delete("/contas/{conta_id}")
def deletar_conta(
    conta_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conta = (
        db.query(Conta)
        .join(Carteira)
        .filter(
            Conta.id == conta_id,
            Carteira.id == Conta.id_carteira,
            Carteira.id_user == user.id
        )
        .first()
    )

    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada ou não pertence ao usuário.")

    # Deleta os robôs vinculados a essa conta
    robos = db.query(RoboDoUser).filter(RoboDoUser.id_conta == conta.id).all()
    for robo in robos:
        db.delete(robo)

    db.delete(conta)
    db.commit()

    return {"detail": "Conta e robôs vinculados deletados com sucesso."}


# 9. DELETE /cliente/robos_do_user/{robo_user_id}
@router.delete("/robos_do_user/{robo_user_id}")
def deletar_robo_do_user(
    robo_user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    robo = (
        db.query(RoboDoUser)
        .filter(
            RoboDoUser.id == robo_user_id,
            RoboDoUser.id_user == user.id
        )
        .first()
    )

    if not robo:
        raise HTTPException(status_code=404, detail="Robô do usuário não encontrado.")

    db.delete(robo)
    db.commit()

    return {"detail": "Robô do usuário deletado com sucesso."}
