# routers/paginas_dinamicas.py
# -*- coding: utf-8 -*-
import os
import time
import re
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from services.deploy_pages_service import GitHubPagesDeployer

# >>> ADD: DB
from sqlalchemy import text
from database import engine

# >>> ADD: GitHub dispatch (apenas BaseModel para o body do DELETE)
from pydantic import BaseModel

router = APIRouter(prefix="/paginas-dinamicas", tags=["Páginas Dinâmicas"])

BASE_UPLOADS_DIR = os.getenv("BASE_UPLOADS_DIR", "/var/www/uploads")
BASE_UPLOADS_URL = os.getenv("BASE_UPLOADS_URL")  # ex.: https://gestordecapitais.com/uploads

# Valores permitidos (casam com os ENUMs do Postgres)
DOMINIO_ENUM = {"pinacle.com.br", "gestordecapitais.com", "tetramusic.com.br"}
FRONTBACK_ENUM = {"frontend", "backend", "fullstack"}  # gestor_capitais.frontbackenum
ESTADO_ENUM = {"producao", "beta", "dev", "desativado"}  # global.estado_enum

# =====================================================================
# POST /criar  (cria SEMPRE uma nova linha/“versão”)
# =====================================================================

@router.post("/criar", status_code=201)
async def criar_pagina_dinamica(
    dominio: str = Form(...),
    slug: str = Form(...),
    arquivo_zip: UploadFile = File(...),
    # >>> NOVOS CAMPOS (opcionais)
    front_ou_back: str | None = Form(None),
    estado: str | None = Form(None),
):
    # 1) validações
    if not re.fullmatch(r"[a-z0-9-]{1,64}", slug):
        raise HTTPException(status_code=400, detail="Slug inválido. Use [a-z0-9-]{1,64}.")
    if dominio not in DOMINIO_ENUM:
        raise HTTPException(status_code=400, detail="Domínio inválido para global.dominio_enum.")
    if front_ou_back is not None and front_ou_back not in FRONTBACK_ENUM:
        raise HTTPException(status_code=400, detail="front_ou_back inválido (frontend|backend|fullstack).")
    if estado is not None and estado not in ESTADO_ENUM:
        raise HTTPException(status_code=400, detail="estado inválido (producao|beta|dev|desativado).")

    # 2) salvar ZIP em pasta pública
    if not BASE_UPLOADS_URL:
        raise HTTPException(status_code=500, detail="BASE_UPLOADS_URL não configurado.")
    os.makedirs(BASE_UPLOADS_DIR, exist_ok=True)

    ts = int(time.time())
    fname = f"{slug}-{ts}.zip"
    fpath = os.path.join(BASE_UPLOADS_DIR, fname)

    data = await arquivo_zip.read()  # ler UMA vez e reutilizar
    with open(fpath, "wb") as f:
        f.write(data)

    zip_url = f"{BASE_UPLOADS_URL}/{fname}"

    # 3) salvar NO BANCO (sempre cria uma nova linha/versão)
    url_full = f"https://{dominio}/p/{slug}/"
    db_saved = False
    try:
        # Nota: CAST com tipos qualificados por schema:
        # - global.dominio_enum
        # - gestor_capitais.frontbackenum
        # - global.estado_enum
        sql = text("""
            INSERT INTO global.paginas_dinamicas
                (dominio, slug, arquivo_zip, url_completa, front_ou_back, estado)
            VALUES
                (CAST(:dominio AS global.dominio_enum),
                 :slug,
                 :arquivo_zip,
                 :url_completa,
                 CAST(:front_ou_back AS gestor_capitais.frontbackenum),
                 CAST(:estado AS global.estado_enum))
        """)
        with engine.begin() as conn:
            conn.execute(sql, {
                "dominio": dominio,
                "slug": slug,
                "arquivo_zip": data,
                "url_completa": url_full,
                "front_ou_back": front_ou_back,  # pode ser None -> CAST(NULL AS …) é aceito
                "estado": estado,                # idem
            })
        db_saved = True
    except Exception as e:
        logging.getLogger("paginas_dinamicas").warning(
            "Falha ao inserir nova versão em global.paginas_dinamicas: %s", e
        )

    # 4) disparar o workflow (sem 'kind' ou 'zip_path')
    try:
        GitHubPagesDeployer().dispatch(domain=dominio, slug=slug, zip_url=zip_url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Página salva, mas o deploy falhou: {e}")

    return {
        "ok": True,
        "dominio": dominio,
        "slug": slug,
        "zip_url": zip_url,
        "url": url_full,
        "front_ou_back": front_ou_back,
        "estado": estado,
        "db_saved": db_saved,
    }

# =====================================================================
# DELETE /delete  -> dispara Actions e apaga do banco
# =====================================================================

class DeleteBody(BaseModel):
    dominio: str
    slug: str

@router.delete(
    "/delete",
    summary="paginas_dinamicas delete",
    description="Dispara exclusão no GitHub Actions e remove o registro na tabela paginas_dinamicas."
)
def paginas_dinamicas_delete(body: DeleteBody):
    dominio = body.dominio
    slug = body.slug

    # mesmas validações mínimas do POST
    if not re.fullmatch(r"[a-z0-9-]{1,64}", slug):
        raise HTTPException(status_code=400, detail="Slug inválido. Use [a-z0-9-]{1,64}.")
    if dominio not in DOMINIO_ENUM:
        raise HTTPException(status_code=400, detail="Domínio inválido.")

    # 1) Disparar o workflow de delete usando a MESMA classe/config do deploy
    try:
        GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=slug)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao disparar delete no GitHub: {e}")

    # 2) Apagar do banco (CAST para global.dominio_enum)
    try:
        with engine.begin() as conn:
            res = conn.execute(
                text("""
                    DELETE FROM global.paginas_dinamicas
                    WHERE dominio = CAST(:d AS global.dominio_enum)
                      AND slug    = :s
                """),
                {"d": dominio, "s": slug},
            )
            apagado_no_banco = (res.rowcount or 0) > 0
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub ok, mas erro ao excluir no banco: {e}")

    return {
        "ok": True,
        "github_action": {"workflow": "delete-landing"},
        "apagado_no_banco": apagado_no_banco,
        "dominio": dominio,
        "slug": slug,
    }
