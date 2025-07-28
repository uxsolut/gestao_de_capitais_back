from fastapi import APIRouter, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from models.robos_do_user import RobosDoUser
from schemas.robos_do_user import RoboDoUser
from models.robos import Robo
from models.users import User
from auth.dependencies import get_db, get_current_user

router = APIRouter(prefix="/robos_do_user", tags=["Robôs do Usuário"])

# ---------- GET: Listar robôs do user ----------
@router.get("/listar", response_model=List[RoboDoUser])
def listar_robos_do_user(
    id_robo_user: Optional[int] = None,
    id_conta: Optional[int] = None,  # 🔍 novo filtro aqui
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(RobosDoUser).filter(RobosDoUser.id_user == current_user.id)

    if id_robo_user is not None:
        query = query.filter(RobosDoUser.id == id_robo_user)
    
    if id_conta is not None:
        query = query.filter(RobosDoUser.id_conta == id_conta)

    return query.all()

# ---------- POST: Criar robô do user ----------
@router.post("/", response_model=RoboDoUser)
def criar_robo_do_user(
    id_robo: int = Form(...),
    ligado: bool = Form(False),
    ativo: bool = Form(False),
    tem_requisicao: bool = Form(False),
    id_ordem: Optional[int] = Form(None),
    id_carteira: Optional[int] = Form(None),
    id_conta: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verifica duplicidade
    if id_robo is not None and id_conta is not None:
        existente = db.query(RobosDoUser).filter_by(
            id_robo=id_robo, id_conta=id_conta, id_user=current_user.id
        ).first()
        if existente:
            raise HTTPException(
                status_code=400,
                detail="Este robô já está vinculado a esta conta.",
            )

    # Busca o arquivo_user do robô
    robo = db.query(Robo).filter(Robo.id == id_robo).first()
    if not robo:
        raise HTTPException(status_code=404, detail="Robô não encontrado.")

    conteudo = robo.arquivo_user

    novo = RobosDoUser(
        id_user=current_user.id,
        id_robo=id_robo,
        ligado=ligado,
        ativo=ativo,
        tem_requisicao=tem_requisicao,
        id_ordem=id_ordem,
        id_carteira=id_carteira,
        id_conta=id_conta,
        arquivo_cliente=conteudo
    )

    db.add(novo)
    db.commit()
    db.refresh(novo)

    return novo
