import os, time, re, logging
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

# =====================================================================
# POST /criar  (AGORA INSERE SEMPRE UMA NOVA LINHA/“VERSÃO”)
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

    # 3) SALVAR NO BANCO (sempre cria uma nova linha/versão)
    url_full = f"https://{dominio}/p/{slug}/"
    db_saved = False
    try:
        sql = text("""
            INSERT INTO paginas_dinamicas (dominio, slug, arquivo_zip, url_completa)
            VALUES (CAST(:dominio AS dominio_enum), :slug, :arquivo_zip, :url_completa)
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
            "Falha ao inserir nova versão em paginas_dinamicas: %s", e
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
# DELETE /delete  -> dispara Actions (usando MESMA classe) e apaga do banco
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
    if not re.fullmatch(r"[a-z0-9.-]+", dominio):
        raise HTTPException(status_code=400, detail="Domínio inválido.")

    # 1) Disparar o workflow de delete usando a MESMA classe/config do deploy
    try:
        GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=slug)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao disparar delete no GitHub: {e}")

    # 2) Apagar do banco (CAST para dominio_enum)
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
        raise HTTPException(status_code=502, detail=f"GitHub ok, mas erro ao excluir no banco: {e}")

    return {
        "ok": True,
        "github_action": {"workflow": "delete-landing"},
        "apagado_no_banco": apagado_no_banco,
        "dominio": dominio,
        "slug": slug,
    }
