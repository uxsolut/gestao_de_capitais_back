from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from auth.dependencies import get_db, get_current_user
from schemas.dashboard import DashboardResponse, DashboardMetricas, DashboardResumoDados
from models.users import User
from models.carteiras import Carteira
from models.robos_do_user import RobosDoUser
from models.ordens import Ordem

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/", response_model=DashboardResponse)
def get_dashboard_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    carteiras = db.query(Carteira).filter(Carteira.id_user == current_user.id).all()
    robos = db.query(RobosDoUser).filter(RobosDoUser.id_user == current_user.id).all()
    ordens = db.query(Ordem).filter(Ordem.id_user == current_user.id).all()

    metricas = DashboardMetricas(
        total_carteiras=len(carteiras),
        total_robos=len(robos),
        total_ordens=len(ordens)
    )

    resumo = DashboardResumoDados(
        carteiras_recentes=[c.nome for c in carteiras[-5:]],
        ordens_recentes=[f"{o.tipo} ({o.conta_meta_trader})" for o in ordens[-5:]]
    )

    return DashboardResponse(metricas=metricas, resumo=resumo)
