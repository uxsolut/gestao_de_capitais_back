# routers/projetos.py
# -*- coding: utf-8 -*-
import os
import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.projeto import Projeto as ProjetoModel
from models.paginas_dinamicas import PaginaDinamica as PaginaModel
from schemas.projeto import Projeto, ProjetoCreate
from services.deploy_pages_service import GitHubPagesDeployer

router = APIRouter(prefix="/projetos", tags=["Projetos"])

BASE_UPLOADS_DIR = os.getenv("BASE_UPLOADS_DIR", "/var/www/uploads")
BASE_UPLOADS_URL = os.getenv("BASE_UPLOADS_URL")  # ex.: https://gestordecapitais.com/uploads


# ---------- POST: Criar novo projeto (seu endpoint existente) ----------
@router.post("/", response_model=Projeto)
def criar_projeto(
    projeto: ProjetoCreate,
    db: Session = Depends(get_db),
):
    novo = ProjetoModel(**projeto.dict())
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


# ---------- PUT: Definir qual versão usar e disparar deploy ----------
@router.put("/{projeto_id}/usar-pagina/{pagina_id}", response_model=Projeto)
def usar_pagina_em_uso(
    projeto_id: int,
    pagina_id: int,
    db: Session = Depends(get_db),
):
    """
    Atualiza projetos.id_pagina_em_uso para a versão informada (pagina_id) e
    dispara o deploy dessa versão (substitui o que está online).
    """
    if not BASE_UPLOADS_URL:
        raise HTTPException(500, "BASE_UPLOADS_URL não configurado no backend.")
    os.makedirs(BASE_UPLOADS_DIR, exist_ok=True)

    projeto = db.get(ProjetoModel, projeto_id)
    if not projeto:
        raise HTTPException(404, "Projeto não encontrado")

    pagina = db.get(PaginaModel, pagina_id)
    if not pagina:
        raise HTTPException(404, "Página/versão não encontrada")

    # Verifica se a URL do projeto corresponde à URL da versão escolhida
    def _norm(u: str) -> str:
        u = u.rstrip("/")
        if u.startswith("https://"):
            u = u[len("https://"):]
        elif u.startswith("http://"):
            u = u[len("http://"):]
        return u

    url_projeto_norm = _norm(projeto.nome)
    url_pagina_norm = _norm(f"https://{pagina.dominio}/p/{pagina.slug}/")
    if url_projeto_norm != url_pagina_norm:
        raise HTTPException(
            status_code=409,
            detail=f"O projeto.nome ('{projeto.nome}') não corresponde à URL da versão escolhida ('https://{pagina.dominio}/p/{pagina.slug}/')."
        )

    # 1) Atualiza o ponteiro
    projeto.id_pagina_em_uso = pagina.id
    db.add(projeto)
    db.commit()
    db.refresh(projeto)

    # 2) Publica o ZIP dessa versão em uma URL pública e dispara o deploy
    ts = int(time.time())
    fname = f"pagina-{pagina.id}-{ts}.zip"
    fpath = os.path.join(BASE_UPLOADS_DIR, fname)
    try:
        with open(fpath, "wb") as f:
            f.write(pagina.arquivo_zip)
    except Exception as e:
        raise HTTPException(500, f"Falha ao materializar ZIP no servidor: {e}")

    zip_url = f"{BASE_UPLOADS_URL}/{fname}"

    try:
        GitHubPagesDeployer().dispatch(domain=pagina.dominio, slug=pagina.slug, zip_url=zip_url)
    except Exception as e:
        # ponteiro já foi atualizado; retornamos 502 para você ver o erro do deploy
        raise HTTPException(status_code=502, detail=f"Ponteiro atualizado, mas deploy falhou: {e}")

    return projeto
