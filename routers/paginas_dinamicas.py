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

# >>> ADD: typing (somente adição, não altera nada do que já existia)
from typing import Optional, List, Tuple

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
    new_id: Optional[int] = None
    removidos_ids: List[int] = []

    try:
        # Usamos NULLIF(..., '') para garantir que string vazia → NULL antes do CAST
        with engine.begin() as conn:
            row = conn.execute(
                text("""
                    INSERT INTO global.paginas_dinamicas
                        (dominio, slug, arquivo_zip, url_completa, front_ou_back, estado)
                    VALUES
                        (CAST(:dominio AS global.dominio_enum),
                         :slug,
                         :arquivo_zip,
                         :url_completa,
                         CAST(NULLIF(:front_ou_back, '') AS gestor_capitais.frontbackenum),
                         CAST(NULLIF(:estado, '')        AS global.estado_enum))
                    RETURNING id, dominio::text AS dominio, slug, estado::text AS estado
                """),
                {
                    "dominio": dominio,
                    "slug": slug,
                    "arquivo_zip": data,
                    "url_completa": url_full,
                    "front_ou_back": front_ou_back or "",  # vazio para o NULLIF tratar
                    "estado": estado or "",
                },
            ).mappings().first()

            new_id = int(row["id"])
            db_saved = True

            # **Regra de substituição automática somente para estados ativos**
            if estado in {"producao", "beta", "dev"}:
                res = conn.execute(
                    text("""
                        UPDATE global.paginas_dinamicas
                           SET estado = 'desativado'::global.estado_enum
                         WHERE dominio = CAST(:dom AS global.dominio_enum)
                           AND slug    = :slug
                           AND estado  = CAST(:est AS global.estado_enum)
                           AND id     <> :id
                        RETURNING id
                    """),
                    {"dom": dominio, "slug": slug, "est": estado, "id": new_id},
                )
                removidos_ids = [r[0] for r in res.fetchall()]

    except Exception as e:
        db_error = f"{e.__class__.__name__}: {e}"
        logging.getLogger("paginas_dinamicas").warning(
            "Falha ao inserir/substituir em global.paginas_dinamicas: %s", db_error
        )

    # 4) deploy conforme estado
    try:
        # 4.a) remover o(s) antigo(s) do mesmo (dominio, slug, estado) se existirem
        if removidos_ids:
            slug_remove = _deploy_slug(slug, estado)  # 'slug' | 'beta/slug' | 'dev/slug'
            if slug_remove:
                GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=slug_remove)

        # 4.b) publicar o novo se estado for ativo
        if estado in {"producao", "beta", "dev"}:
            slug_deploy = _deploy_slug(slug, estado)
            GitHubPagesDeployer().dispatch(domain=dominio, slug=slug_deploy, zip_url=zip_url)
        elif estado is None:
            # compat: se não informar estado, manter comportamento antigo (deploy em /p/slug/)
            GitHubPagesDeployer().dispatch(domain=dominio, slug=slug, zip_url=zip_url)
        # se estado == 'desativado', não publica nada
    except Exception as e:
        # se o deploy falhar, mas o DB salvou, retornamos erro de gateway
        raise HTTPException(
            status_code=502,
            detail=f"Página salva={db_saved}, id={new_id}, mas o deploy falhou: {e}"
        )

    return {
        "ok": True,
        "id": new_id,
        "dominio": dominio,
        "slug": slug,
        "zip_url": zip_url,
        "url": url_full,
        "front_ou_back": front_ou_back,
        "estado": estado,
        "desativados_ids": removidos_ids or [],
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


# ======================= (NOVO) EDIÇÃO DE ESTADO =======================

# helpers (apenas adicionados)
def _deploy_slug(slug: str, estado: Optional[str]) -> Optional[str]:
    """
    Retorna o 'slug' que será enviado ao deploy considerando o estado.
      - producao -> 'slug'
      - beta/dev -> 'beta/slug' ou 'dev/slug'
      - desativado/None -> None
    """
    if not estado or estado == "desativado":
        return None
    if estado == "producao":
        return slug
    return f"{estado}/{slug}"  # beta/dev

def _materializar_zip(slug: str, rec_id: int, data: bytes) -> Tuple[str, str]:
    """
    Salva o bytea do banco como arquivo .zip público e retorna (path, url).
    """
    if not BASE_UPLOADS_URL:
        raise HTTPException(status_code=500, detail="BASE_UPLOADS_URL não configurado.")
    os.makedirs(BASE_UPLOADS_DIR, exist_ok=True)
    ts = int(time.time())
    fname = f"{slug}-{rec_id}-{ts}.zip"
    fpath = os.path.join(BASE_UPLOADS_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(data)
    return fpath, f"{BASE_UPLOADS_URL}/{fname}"

class EditarEstadoBody(BaseModel):
    id: int
    estado: str  # 'producao' | 'beta' | 'dev' | 'desativado'

@router.put(
    "/editar-estado",
    summary="Atualiza o estado (producao/beta/dev/desativado) e gerencia deploys",
)
def editar_estado(body: EditarEstadoBody):
    novo_estado = (body.estado or "").strip()
    if novo_estado not in ESTADO_ENUM:
        raise HTTPException(status_code=400, detail="estado inválido (producao|beta|dev|desativado).")

    # 1) Ler o registro alvo
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT id,
                       dominio::text AS dominio,
                       slug,
                       estado::text AS estado,
                       arquivo_zip
                FROM global.paginas_dinamicas
                WHERE id = :id
                LIMIT 1
            """),
            {"id": body.id},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")

    dominio = row["dominio"]
    slug = row["slug"]
    estado_atual = row["estado"]  # pode ser None
    arquivo_zip = row["arquivo_zip"]

    if dominio not in DOMINIO_ENUM:
        raise HTTPException(status_code=400, detail="Domínio inválido no registro.")

    # 2) Transação: garantir exclusividade por (dominio, slug, estado ativo) e atualizar alvo
    removidos_ids: List[int] = []
    estado_path_old = _deploy_slug(slug, estado_atual)
    estado_path_new = _deploy_slug(slug, novo_estado)

    with engine.begin() as conn:
        # 2.1) Se novo estado for ativo, desativar outro que já esteja no mesmo estado para mesma URL
        if novo_estado in {"producao", "beta", "dev"}:
            res = conn.execute(
                text("""
                    UPDATE global.paginas_dinamicas
                       SET estado = 'desativado'::global.estado_enum
                     WHERE dominio = CAST(:dom AS global.dominio_enum)
                       AND slug    = :slug
                       AND estado  = CAST(:est AS global.estado_enum)
                       AND id     <> :id
                    RETURNING id
                """),
                {"dom": dominio, "slug": slug, "est": novo_estado, "id": body.id},
            )
            removidos_ids = [r[0] for r in res.fetchall()]

        # 2.2) Atualizar o alvo para o novo estado
        conn.execute(
            text("""
                UPDATE global.paginas_dinamicas
                   SET estado = CAST(:est AS global.estado_enum)
                 WHERE id = :id
            """),
            {"est": novo_estado, "id": body.id},
        )

    # 3) Pós-transação: acionar GitHub Actions

    # 3.a) Remover deploy do(s) que foram desativados por conflito (mesmo estado/URL)
    try:
        if removidos_ids:
            slug_remove = _deploy_slug(slug, novo_estado)  # 'slug' ou 'beta/slug' ou 'dev/slug'
            if slug_remove:
                GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=slug_remove)
    except Exception as e:
        logging.getLogger("paginas_dinamicas").warning(
            "Falha ao remover deploy anterior (%s): %s", removidos_ids, e
        )

    # 3.b) Se o novo estado for desativado, tirar do ar o próprio alvo (usando o estado antigo)
    if novo_estado == "desativado":
        try:
            if estado_path_old:
                GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=estado_path_old)
        except Exception as e:
            logging.getLogger("paginas_dinamicas").warning(
                "Falha ao remover deploy do alvo (id=%s): %s", body.id, e
            )
        return {
            "ok": True,
            "id": body.id,
            "dominio": dominio,
            "slug": slug,
            "novo_estado": novo_estado,
            "desativados_ids": removidos_ids,
            "deploy": {"action": "delete", "slug_removed": estado_path_old},
        }

    # 3.c) Novo estado ativo => deploy do alvo na rota correta
    try:
        _, zip_url = _materializar_zip(slug, body.id, arquivo_zip)
        slug_deploy = estado_path_new  # 'slug' ou 'beta/slug' ou 'dev/slug'
        GitHubPagesDeployer().dispatch(domain=dominio, slug=slug_deploy, zip_url=zip_url)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Estado atualizado, mas falha ao disparar deploy do novo estado: {e}"
        )

    return {
        "ok": True,
        "id": body.id,
        "dominio": dominio,
        "slug": slug,
        "novo_estado": novo_estado,
        "desativados_ids": removidos_ids,
        "deploy": {"action": "deploy", "slug_deploy": slug_deploy, "zip_url": zip_url},
    }
