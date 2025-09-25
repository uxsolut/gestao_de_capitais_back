# routers/aplicacoes.py
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
from typing import Optional, List, Tuple

router = APIRouter(prefix="/aplicacoes", tags=["Aplicações"])

BASE_UPLOADS_DIR = os.getenv("BASE_UPLOADS_DIR", "/var/www/uploads")
BASE_UPLOADS_URL = os.getenv("BASE_UPLOADS_URL")  # ex.: https://gestordecapitais.com/uploads

# Valores válidos (iguais aos ENUMs no Postgres)
DOMINIO_ENUM = {"pinacle.com.br", "gestordecapitais.com", "tetramusic.com.br"}
FRONTBACK_ENUM = {"frontend", "backend", "fullstack"}
ESTADO_ENUM = {"producao", "beta", "dev", "desativado"}


# ======================= Helpers =======================

def _is_producao(estado: Optional[str]) -> bool:
    return (estado or "producao") == "producao"

def _canonical_url(dominio: str, estado: Optional[str], slug: Optional[str]) -> str:
    """
    URL pública SEM '/p':

    - producao:
        - sem slug -> https://dominio/
        - com slug -> https://dominio/<slug>
    - beta/dev:
        - sem slug -> https://dominio/<estado>
        - com slug -> https://dominio/<estado>/<slug>
    """
    base = f"https://{dominio}".rstrip("/")
    s = (slug or "").strip("/")
    if _is_producao(estado):
        return f"{base}/" if not s else f"{base}/{s}"
    e = (estado or "").strip("/")
    return f"{base}/{e}" if not s else f"{base}/{e}/{s}"

def _deploy_slug(slug: Optional[str], estado: Optional[str]) -> Optional[str]:
    """
    Caminho enviado ao workflow (SEM '/p'):
      - producao:    '' (raiz) ou '<slug>'
      - beta/dev:    'beta' | 'dev' | 'beta/<slug>' | 'dev/<slug>'
      - desativado/None: None (não publicar)
    """
    if not estado or estado == "desativado":
        return None
    if estado == "producao":
        return (slug or "")  # '' = raiz
    return f"{estado}/{slug}" if slug else estado

def _normalize_slug(raw: Optional[str]) -> Optional[str]:
    s = (raw or "").strip()
    return s or None

def _validate_inputs(dominio: str, slug: Optional[str], front_ou_back: Optional[str], estado: Optional[str]):
    if dominio not in DOMINIO_ENUM:
        raise HTTPException(status_code=400, detail="Domínio inválido para global.dominio_enum.")
    if slug is not None and not re.fullmatch(r"[a-z0-9-]{1,64}", slug):
        raise HTTPException(status_code=400, detail="Slug inválido. Use [a-z0-9-]{1,64}.")
    if front_ou_back is not None and front_ou_back not in FRONTBACK_ENUM:
        raise HTTPException(status_code=400, detail="front_ou_back inválido (frontend|backend|fullstack).")
    if estado is not None and estado not in ESTADO_ENUM:
        raise HTTPException(status_code=400, detail="estado inválido (producao|beta|dev|desativado).")


# ======================= POST (criar) =======================

@router.post("/criar", status_code=201)
async def criar_aplicacao(
    dominio: str = Form(...),
    slug: Optional[str] = Form(None),                 # agora opcional
    arquivo_zip: UploadFile = File(...),
    front_ou_back: str | None = Form(None),
    estado: str | None = Form(None),
    id_empresa: int | None = Form(None),
):
    # 1) normalizar + validar
    slug = _normalize_slug(slug)                      # '' -> None
    front_ou_back = _normalize_slug(front_ou_back)
    estado = _normalize_slug(estado)
    _validate_inputs(dominio, slug, front_ou_back, estado)

    # 2) salvar ZIP em pasta pública
    if not BASE_UPLOADS_URL:
        raise HTTPException(status_code=500, detail="BASE_UPLOADS_URL não configurado.")
    os.makedirs(BASE_UPLOADS_DIR, exist_ok=True)

    ts = int(time.time())
    fname = f"{(slug or 'root')}-{ts}.zip"
    fpath = os.path.join(BASE_UPLOADS_DIR, fname)

    data = await arquivo_zip.read()
    with open(fpath, "wb") as f:
        f.write(data)

    zip_url = f"{BASE_UPLOADS_URL.rstrip('/')}/{fname}"

    # 3) calcular URL final (SEM /p)
    url_full = _canonical_url(dominio, estado, slug)

    # 4) desativar conflitantes (se ativo) e inserir nova linha
    db_saved = False
    db_error = None
    new_id: Optional[int] = None
    removidos_ids: List[int] = []

    try:
        with engine.begin() as conn:
            # 4.1) Se estado for ativo, DESATIVAR antes de inserir (slug null-aware)
            if estado in {"producao", "beta", "dev"}:
                res = conn.execute(
                    text("""
                        UPDATE global.aplicacoes
                           SET estado = 'desativado'::global.estado_enum
                         WHERE dominio = CAST(:dom AS global.dominio_enum)
                           AND slug IS NOT DISTINCT FROM :slug
                           AND estado  = CAST(:est AS global.estado_enum)
                        RETURNING id
                    """),
                    {"dom": dominio, "slug": slug, "est": estado},
                )
                removidos_ids = [r[0] for r in res.fetchall()]

            # 4.2) Inserir a nova versão
            row = conn.execute(
                text("""
                    INSERT INTO global.aplicacoes
                        (dominio, slug, arquivo_zip, url_completa, front_ou_back, estado, id_empresa)
                    VALUES
                        (CAST(:dominio AS global.dominio_enum),
                         :slug,
                         :arquivo_zip,
                         :url_completa,
                         CAST(NULLIF(:front_ou_back, '') AS gestor_capitais.frontbackenum),
                         CAST(NULLIF(:estado, '')        AS global.estado_enum),
                         :id_empresa)
                    RETURNING id,
                              dominio::text AS dominio,
                              slug,
                              estado::text  AS estado,
                              id_empresa
                """),
                {
                    "dominio": dominio,
                    "slug": slug,                     # pode ser None
                    "arquivo_zip": data,
                    "url_completa": url_full,
                    "front_ou_back": front_ou_back or "",
                    "estado": estado or "",
                    "id_empresa": id_empresa,
                },
            ).mappings().first()

            new_id = int(row["id"])
            db_saved = True

    except Exception as e:
        db_error = f"{e.__class__.__name__}: {e}"
        logging.getLogger("aplicacoes").warning(
            "Falha ao inserir/substituir em global.aplicacoes: %s", db_error
        )

    # 5) deploy conforme estado
    try:
        # 5.a) remover o(s) antigo(s) do mesmo (dominio, [slug], estado) se existirem
        if removidos_ids:
            slug_remove = _deploy_slug(slug, estado)  # '', 'slug', 'beta', 'beta/slug', ...
            if slug_remove is not None:
                GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=slug_remove)

        # 5.b) publicar o novo se estado for ativo
        if estado in {"producao", "beta", "dev"}:
            slug_deploy = _deploy_slug(slug, estado)
            GitHubPagesDeployer().dispatch(domain=dominio, slug=slug_deploy or "", zip_url=zip_url)
        elif estado is None:
            # compat antigo → considerar produção
            slug_deploy = _deploy_slug(slug, "producao")
            GitHubPagesDeployer().dispatch(domain=dominio, slug=slug_deploy or "", zip_url=zip_url)
        # se estado == 'desativado', não publica nada
    except Exception as e:
        # se o deploy falhar, mas o DB salvou, retornamos erro de gateway
        raise HTTPException(
            status_code=502,
            detail=f"Aplicação salva={db_saved}, id={new_id}, mas o deploy falhou: {e}"
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
        "id_empresa": id_empresa,
        "desativados_ids": removidos_ids or [],
        "db_saved": db_saved,
        **({"db_error": db_error} if not db_saved and db_error else {}),
    }


# ======================= DELETE (por id) =======================

class DeleteBody(BaseModel):
    id: int  # deletar por ID, simples


@router.delete(
    "/delete",
    summary="aplicacoes delete (por id)",
    description="Remove o deploy (se estiver no ar) e apaga o registro pelo id.",
)
def aplicacoes_delete(body: DeleteBody):
    # 1) Buscar o registro pelo id
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT id,
                       dominio::text AS dominio,
                       slug,
                       estado::text  AS estado
                FROM global.aplicacoes
                WHERE id = :id
                LIMIT 1
            """),
            {"id": body.id},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")

    dominio = row["dominio"]
    slug = row["slug"]           # pode ser None
    estado = row["estado"]       # pode ser None

    # 2) Se estava publicado (producao/beta/dev), remover do GitHub no caminho correto
    slug_path: Optional[str] = None
    try:
        slug_path = _deploy_slug(slug, estado)  # '', 'slug', 'beta', 'beta/slug' | None
        if slug_path is not None:
            GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=slug_path or "")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao disparar delete no GitHub: {e}")

    # 3) Apagar do banco pelo id
    try:
        with engine.begin() as conn:
            res = conn.execute(
                text("DELETE FROM global.aplicacoes WHERE id = :id"),
                {"id": body.id},
            )
            apagado_no_banco = (res.rowcount or 0) > 0
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub ok, mas erro ao excluir no banco: {e}")

    return {
        "ok": True,
        "id": body.id,
        "dominio": dominio,
        "slug": slug,
        "estado": estado,
        "github_action": {"workflow": "delete-landing", "slug_removed": slug_path},
        "apagado_no_banco": apagado_no_banco,
    }


# ======================= EDIÇÃO DE ESTADO =======================

def _materializar_zip(slug: Optional[str], rec_id: int, data: bytes) -> Tuple[str, str]:
    """
    Salva o bytea do banco como arquivo .zip público e retorna (path, url).
    """
    if not BASE_UPLOADS_URL:
        raise HTTPException(status_code=500, detail="BASE_UPLOADS_URL não configurado.")
    os.makedirs(BASE_UPLOADS_DIR, exist_ok=True)
    ts = int(time.time())
    fname = f"{(slug or 'root')}-{rec_id}-{ts}.zip"
    fpath = os.path.join(BASE_UPLOADS_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(data)
    return fpath, f"{BASE_UPLOADS_URL.rstrip('/')}/{fname}"


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
                       estado::text  AS estado,
                       arquivo_zip
                FROM global.aplicacoes
                WHERE id = :id
                LIMIT 1
            """),
            {"id": body.id},
        ).mappings().first()

    if not row:
        raise HTTPException(statuscode=404, detail="Registro não encontrado.")

    dominio = row["dominio"]
    slug = row["slug"]               # pode ser None
    estado_atual = row["estado"]     # pode ser None
    arquivo_zip = row["arquivo_zip"]

    if dominio not in DOMINIO_ENUM:
        raise HTTPException(status_code=400, detail="Domínio inválido no registro.")

    # 2) Transação: garantir exclusividade por (dominio, [slug], estado ativo) e atualizar alvo
    removidos_ids: List[int] = []
    estado_path_old = _deploy_slug(slug, estado_atual)
    estado_path_new = _deploy_slug(slug, novo_estado)

    with engine.begin() as conn:
        # 2.1) Se novo estado for ativo, desativar outro que já esteja no mesmo estado para mesma URL (slug null-aware)
        if novo_estado in {"producao", "beta", "dev"}:
            res = conn.execute(
                text("""
                    UPDATE global.aplicacoes
                       SET estado = 'desativado'::global.estado_enum
                     WHERE dominio = CAST(:dom AS global.dominio_enum)
                       AND slug IS NOT DISTINCT FROM :slug
                       AND estado  = CAST(:est AS global.estado_enum)
                       AND id     <> :id
                    RETURNING id
                """),
                {"dom": dominio, "slug": slug, "est": novo_estado, "id": body.id},
            )
            removidos_ids = [r[0] for r in res.fetchall()]

        # 2.2) Atualizar o alvo para o novo estado e recalcular url_completa (SEM /p)
        nova_url = _canonical_url(dominio, novo_estado, slug)
        conn.execute(
            text("""
                UPDATE global.aplicacoes
                   SET estado = CAST(:est AS global.estado_enum),
                       url_completa = :url
                 WHERE id = :id
            """),
            {"est": novo_estado, "url": nova_url, "id": body.id},
        )

    # 3) Pós-transação: acionar GitHub Actions

    # 3.a) Remover deploy do(s) que foram desativados por conflito (mesmo estado/URL)
    try:
        if removidos_ids:
            slug_remove = _deploy_slug(slug, novo_estado)  # '', 'slug', 'beta', 'beta/slug'
            if slug_remove is not None:
                GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=slug_remove or "")
    except Exception as e:
        logging.getLogger("aplicacoes").warning(
            "Falha ao remover deploy anterior (%s): %s", removidos_ids, e
        )

    # 3.b) Se o novo estado for desativado, tirar do ar o próprio alvo (usando o estado antigo)
    if novo_estado == "desativado":
        try:
            if estado_path_old is not None:
                GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=estado_path_old or "")
        except Exception as e:
            logging.getLogger("aplicacoes").warning(
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

    # 3.c) Novo estado ativo => deploy do alvo na rota correta (SEM /p)
    try:
        _, zip_url = _materializar_zip(slug, body.id, arquivo_zip)
        slug_deploy = estado_path_new  # '', 'slug', 'beta', 'beta/slug'
        GitHubPagesDeployer().dispatch(domain=dominio, slug=slug_deploy or "", zip_url=zip_url)
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
        "deploy": {"action": "deploy", "slug_deploy": estado_path_new, "zip_url": zip_url},
    }
