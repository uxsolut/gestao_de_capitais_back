from typing import List
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from models.carteiras import Carteira as CarteiraModel
from models.users import User
from schemas.carteiras import Carteira, CarteiraCreate
from auth.dependencies import get_db, get_current_user

router = APIRouter(
    prefix="/carteiras",
    tags=["Carteiras"],
)

@router.get("/", response_model=List[Carteira])
def read_carteiras(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista todas as carteiras do usuário autenticado.
    """
    carteiras = (
        db.query(CarteiraModel)
        .filter(CarteiraModel.id_user == current_user.id)
        .all()
    )
    return carteiras


@router.post("/", response_model=Carteira, status_code=status.HTTP_201_CREATED)
def create_carteira(
    carteira_in: CarteiraCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cria uma nova carteira vinculada ao usuário autenticado.
    """
    nova = CarteiraModel(
        nome=carteira_in.nome,
        id_user=current_user.id
    )

    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova
