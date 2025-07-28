from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from models.versao_aplicacao import VersaoAplicacao as VersaoAplicacaoModel
from schemas.versao_aplicacao import VersaoAplicacao
from auth.dependencies import get_db, get_current_user
from models.users import User
from typing import Optional

router = APIRouter(prefix="/versoes_aplicacao", tags=["Versoes de Aplicação"])

# ---------- POST: Criar nova versão de aplicação ----------
@router.post("/", response_model=VersaoAplicacao)
async def criar_versao_aplicacao(
    descricao: str = Form(...),
    id_aplicacao: Optional[int] = Form(None),  # ✅ novo campo
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conteudo = await arquivo.read()

    nova = VersaoAplicacaoModel(
        descricao=descricao,
        arquivo=conteudo,
        id_user=current_user.id,
        id_aplicacao=id_aplicacao,  # ✅ salvar no banco
    )

    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova
