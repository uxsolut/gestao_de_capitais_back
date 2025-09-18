import os, time, re, logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from services.deploy_pages_service import GitHubPagesDeployer

# >>> ADD: DB
from sqlalchemy import text
from database import engine

# >>> ADD: GitHub dispatch
import requests
from pydantic import BaseModel

router = APIRouter(prefix="/paginas-dinamicas", tags=["Páginas Dinâmicas"])

BASE_UPLOADS_DIR = os.getenv("BASE_UPLOADS_DIR", "/var/www/uploads")
BASE_UPLOADS_URL = os.getenv("BASE_UPLOADS_URL")  # ex.: https://gestordecapitais.com/uploads

# =====================================================================
# POST /criar  (SEU CÓDIGO — INTACTO)
# =====================================================================

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

    data = await arquivo_zip.read()  # <<< ler UMA vez e reutilizar
    with open(fpath, "wb") as f:
        f.write(data)

    zip_url = f"{BASE_UPLOADS_URL}/{fname}"

    # 3) SALVAR NO BANCO (best-effort, não quebra o fluxo)
    url_full = f"https://{dominio}/p/{slug}/"
    db_saved = False
    try:
        sql = text("""
            INSERT INTO paginas_dinamicas (dominio, slug, arquivo_zip, url_completa)
            VALUES (CAST(:dominio AS dominio_enum), :slug, :arquivo_zip, :url_completa)
            ON CONFLICT (dominio, slug) DO UPDATE
               SET arquivo_zip = EXCLUDED.arquivo_zip,
                   url_completa = EXCLUDED.url_completa
        """)
        with engine.begin() as conn:
            conn.execute(sql, {
                "dominio": dominio,
                "slug": slug,
                "arquivo_zip": data,
                "url_completa": url_full,
            })
        db_saved = True
    except Exception as e:
        # não interrompe o deploy; apenas registra
        logging.getLogger("paginas_dinamicas").warning(
            "Falha ao salvar paginas_dinamicas: %s", e
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
        "db_saved": db_saved,
    }

# =====================================================================
# DELETE /delete  (NOVO)  -> dispara Actions e apaga do banco (enum cast)
# =====================================================================

# Env p/ chamar o GitHub Actions (repository_dispatch)
GH_OWNER = os.getenv("GH_OWNER")          # ex.: "uxsolut"
GH_REPO  = os.getenv("GH_REPO")           # ex.: "pages-ops"
GH_TOKEN = os.getenv("GH_TOKEN_REPO")     # PAT com permissão de Repository dispatch / Actions: write
GH_DELETE_EVENT = os.getenv("GH_DELETE_EVENT", "delete-landing")

def _gh_headers():
    if not (GH_OWNER and GH_REPO and GH_TOKEN):
        raise HTTPException(status_code=500, detail="GH_OWNER/GH_REPO/GH_TOKEN_REPO não configurados")
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GH_TOKEN}",
    }

def _dispatch_delete_to_github(domain: str, slug: str):
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/dispatches"
    payload = {"event_type": GH_DELETE_EVENT, "client_payload": {"domain": domain, "slug": slug}}
    r = requests.post(url, headers=_gh_headers(), json=payload, timeout=20)
    if r.status_code != 204:
        raise HTTPException(status_code=502, detail=f"Falha no GitHub: {r.status_code} {r.text}")

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
    if not re.fullmatch(r"[a-z0-9.-]+", dominio):
        raise HTTPException(status_code=400, detail="Domínio inválido.")

    # 1) dispara GitHub Actions p/ apagar /var/www/pages/<dominio>/<slug>
    _dispatch_delete_to_github(dominio, slug)

    # 2) apaga do banco (CAST para dominio_enum)
    try:
        with engine.begin() as conn:
            res = conn.execute(
                text("""
                    DELETE FROM paginas_dinamicas
                    WHERE dominio = CAST(:d AS dominio_enum)
                      AND slug    = :s
                """),
                {"d": dominio, "s": slug},
            )
            apagado_no_banco = (res.rowcount or 0) > 0
    except Exception as e:
        # Se quiser falhar quando não conseguir apagar no banco, mantenha 502
        raise HTTPException(status_code=502, detail=f"GitHub ok, mas erro ao excluir no banco: {e}")

    return {
        "ok": True,
        "github_action": {"event_type": GH_DELETE_EVENT, "repo": f"{GH_OWNER}/{GH_REPO}"},
        "apagado_no_banco": apagado_no_banco,
        "dominio": dominio,
        "slug": slug,
    }
