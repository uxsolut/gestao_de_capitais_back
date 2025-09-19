# routers/paginas_dinamicas.py
# -*- coding: utf-8 -*-
import os
import time
import re
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from services.deploy_pages_service import GitHubPagesDeployer

from sqlalchemy import text
from database import engine

from pydantic import BaseModel

router = APIRouter(prefix="/paginas-dinamicas", tags=["Páginas Dinâmicas"])

BASE_UPLOADS_DIR = os.getenv("BASE_UPLOADS_DIR", "/var/www/uploads")
BASE_UPLOADS_URL = os.getenv("BASE_UPLOADS_URL")  # ex.: https://gestordecapitais.com/uploads

# Valores válidos (iguais aos ENUMs no Postgres)
DOMINIO_ENUM = {"pinacle.com.br", "gestordecapitais.com", "tetramusic.com.br"}
FRONTBACK_ENUM = {"frontend", "backend", "fullstack"}
ESTADO_ENUM = {"producao", "beta", "dev", "desativado"}

@router.post("/criar", status_code=201)
async def criar_pagina_dinamica(
    dominio: str = Form(...),
    slug: str = Form(...),
    arquivo_zip: UploadFile = File(...),
    front_ou_back: str | None = Form(None),
    estado: str | None = Form(None),
):
    # 1) validações simples
    if not re.fullmatch(r"[a-z0-9-]{1,64}", slug):
        raise HTTPException(status_code=400, detail="Slug inválido. Use [a-z0-9-]{1,64}.")
    if dominio not in DOMINIO_ENUM:
        raise HTTPException(status_code=400, detail="Domínio inválido para global.dominio_enum.")
    # normalizar: campos opcionais podem vir como "" no form-data
    front_ou_back = (front_ou_back or "").strip() or None
    estado = (estado or "").strip() or None
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

    data = await arquivo_zip.read()
    with open(fpath, "wb") as f:
        f.write(data)

    zip_url = f"{BASE_UPLOADS_URL}/{fname}"

    # 3) salvar no banco (sempre nova linha/versão)
    url_full = f"https://{dominio}/p/{slug}/"
    db_saved = False
    db_error = None
    try:
        # Usamos NULLIF(..., '') para garantir que string vazia → NULL antes do CAST
        sql = text("""
            INSERT INTO global.paginas_dinamicas
                (dominio, slug, arquivo_zip, url_completa, front_ou_back, estado)
            VALUES
                (CAST(:dominio AS global.dominio_enum),
                 :slug,
                 :arquivo_zip,
                 :url_completa,
                 CAST(NULLIF(:front_ou_back, '') AS gestor_capitais.frontbackenum),
                 CAST(NULLIF(:estado, '')        AS global.estado_enum))
        """)
        with engine.begin() as conn:
            conn.execute(sql, {
                "dominio": dominio,
                "slug": slug,
                "arquivo_zip": data,
                "url_completa": url_full,
                "front_ou_back": front_ou_back or "",  # deixa vazio para o NULLIF tratar
                "estado": estado or "",
            })
        db_saved = True
    except Exception as e:
        db_error = f"{e.__class__.__name__}: {e}"
        logging.getLogger("paginas_dinamicas").warning(
            "Falha ao inserir em global.paginas_dinamicas: %s", db_error
        )

    # 4) dispara workflow
    try:
        GitHubPagesDeployer().dispatch(domain=dominio, slug=slug, zip_url=zip_url)
    except Exception as e:
        # se o deploy falhar, mas o DB salvou, ainda retornamos erro de gateway
        raise HTTPException(status_code=502, detail=f"Página salva={db_saved}, mas o deploy falhou: {e}")

    return {
        "ok": True,
        "dominio": dominio,
        "slug": slug,
        "zip_url": zip_url,
        "url": url_full,
        "front_ou_back": front_ou_back,
        "estado": estado,
        "db_saved": db_saved,
        **({"db_error": db_error} if not db_saved and db_error else {}),
    }


# ======================= DELETE =======================

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

    if not re.fullmatch(r"[a-z0-9-]{1,64}", slug):
        raise HTTPException(status_code=400, detail="Slug inválido. Use [a-z0-9-]{1,64}.")
    if dominio not in DOMINIO_ENUM:
        raise HTTPException(status_code=400, detail="Domínio inválido.")

    try:
        GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=slug)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao disparar delete no GitHub: {e}")

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
