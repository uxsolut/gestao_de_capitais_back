import os, time, re
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from services.deploy_pages_service import GitHubPagesDeployer

router = APIRouter(prefix="/paginas-dinamicas", tags=["Páginas Dinâmicas"])

BASE_UPLOADS_DIR = os.getenv("BASE_UPLOADS_DIR", "/var/www/uploads")
BASE_UPLOADS_URL = os.getenv("BASE_UPLOADS_URL")  # ex.: https://gestordecapitais.com/uploads

@router.post("/criar", status_code=201)
async def criar_pagina_dinamica(
    dominio: str = Form(...),
    slug: str = Form(...),
    arquivo_zip: UploadFile = File(...)
):
    # 1) valida slug
    if not re.fullmatch(r"[a-z0-9-]{1,64}", slug):
        raise HTTPException(status_code=400, detail="Slug inválido. Use [a-z0-9-]{1,64}.")

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

    # 3) (opcional) salvar registro no banco como você já faz
    # ... ex.: inserir dominio/slug/arquivo_zip/url_completa etc.

    # 4) disparar o workflow (sem 'kind' ou 'zip_path')
    try:
        GitHubPagesDeployer().dispatch(domain=dominio, slug=slug, zip_url=zip_url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Página salva, mas o deploy falhou: {e}")

    return {"ok": True, "dominio": dominio, "slug": slug, "zip_url": zip_url}
