# -*- coding: utf-8 -*-
import json
import os
import re
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from database import get_db
from models.paginas_dinamicas import PaginaDinamica
from schemas.paginas_dinamicas import PaginaDinamicaOut
from services.deploy_pages_service import GitHubPagesDeployer

router = APIRouter(prefix="/paginas-dinamicas", tags=["Páginas Dinâmicas"])

SLUG_RE = re.compile(r"^[a-z0-9-]{1,64}$")

@router.post("/", response_model=PaginaDinamicaOut, status_code=status.HTTP_201_CREATED)
async def criar_pagina_dinamica(
    # IMPORTANTE: aqui o "dominio" deve receber exatamente o domínio do seu workflow (ex.: pinacle.com.br)
    dominio: str = Form(..., description="Domínio FQDN, ex.: pinacle.com.br"),
    slug: str = Form(..., description="Slug [a-z0-9-]{1,64}"),
    arquivo_zip: UploadFile = File(..., description="ZIP com index.html na raiz"),
    db: Session = Depends(get_db),
):
    if not SLUG_RE.match(slug):
        raise HTTPException(status_code=422, detail="Slug inválido. Use [a-z0-9-], 1..64 chars.")
    if not arquivo_zip.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=422, detail="Envie um arquivo .zip")
    raw_zip = await arquivo_zip.read()
    if not raw_zip:
        raise HTTPException(status_code=422, detail="ZIP vazio.")

    # Mapa opcional para sobrescrever base URLs (pode deixar vazio)
    # Ex.: BASE_URL_MAP_JSON='{"pinacle.com.br":"https://pinacle.com.br"}'
    try:
        base_url_map = json.loads(os.getenv("BASE_URL_MAP_JSON", "{}"))
    except Exception:
        base_url_map = {}

    deployer = GitHubPagesDeployer()

    # 1) Salva no banco já com URL final no formato do seu Nginx: /p/<slug>/
    url_completa = deployer.build_final_url(dominio, slug, base_url_map)
    pagina = PaginaDinamica(
        dominio=dominio,
        slug=slug,
        arquivo_zip=raw_zip,
        url_completa=url_completa,
    )
    db.add(pagina)
    try:
        db.commit()
        db.refresh(pagina)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erro ao salvar no banco: {e}")

    # 2) Sobe ZIP para o repositório e dispara SEU workflow
    try:
        zip_path = deployer.upload_zip(raw_zip, domain=dominio, slug=slug)
        deployer.dispatch_workflow_zip_repo(domain=dominio, slug=slug, zip_path=zip_path)
    except Exception as e:
        # Registro permanece salvo; reporta falha de deploy
        raise HTTPException(status_code=502, detail=f"Página salva, mas o deploy falhou: {e}")

    return pagina
