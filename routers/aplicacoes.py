# routers/aplicacoes.py
# -*- coding: utf-8 -*-
import os
import time
import re
import logging
from typing import Optional, List, Tuple

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends, status
from pydantic import BaseModel

from sqlalchemy import text
from database import engine

# 🔐 Proteção igual às outras APIs
from auth.dependencies import get_current_user
from models.users import User

from services.deploy_pages_service import GitHubPagesDeployer

router = APIRouter(prefix="/aplicacoes", tags=["Aplicações"])

BASE_UPLOADS_DIR = os.getenv("BASE_UPLOADS_DIR", "/var/www/uploads")
BASE_UPLOADS_URL = os.getenv("BASE_UPLOADS_URL")  # ex.: https://gestordecapitais.com/uploads

# Valores válidos (iguais aos ENUMs no Postgres)
DOMINIO_ENUM = {"pinacle.com.br", "gestordecapitais.com", "tetramusic.com.br"}
FRONTBACK_ENUM = {"frontend", "backend", "fullstack"}
ESTADO_ENUM = {"producao", "beta", "dev", "desativado"}


# =========================================================
#                  MODELS para respostas
# =========================================================
class AplicacaoOut(BaseModel):
    id: int
    dominio: str
    slug: Optional[str] = None
    url_completa: Optional[str] = None
    front_ou_back: Optional[str] = None
    estado: Optional[str] = None
    id_empresa: Optional[int] = None
    precisa_logar: bool


# ======================= Helpers =======================
def _is_producao(estado: Optional[str]) -> bool:
    return (estado or "producao") == "producao"


def _canonical_url(dominio: str, estado: Optional[str], slug: Optional[str]) -> str:
    """
    URL pública SEM '/p':
    - producao:  https://dominio/  ou  https://dominio/<slug>
    - beta/dev:  https://dominio/<estado>  ou  https://dominio/<estado>/<slug>
    """
    base = f"https://{dominio}".rstrip("/")
    s = (slug or "").strip("/")
    if _is_producao(estado):
        return f"{base}/" if not s else f"{base}/{s}"
    e = (estado or "").strip("/")
    return f"{base}/{e}" if not s else f"{base}/{e}/{s}"


def _deploy_slug(slug: Optional[str], estado: Optional[str]) -> Optional[str]:
    if not estado or estado == "desativado":
        return None
    if estado == "producao":
        return (slug or "")  # '' = raiz
    return f"{estado}/{slug}" if slug else estado


def _normalize_slug(raw: Optional[str]) -> Optional[str]:
    s = (raw or "").strip()
    return s or None


def _validate_inputs(dominio: Optional[str], slug: Optional[str], front_ou_back: Optional[str], estado: Optional[str]):
    if dominio is not None and dominio not in DOMINIO_ENUM:
        raise HTTPException(status_code=400, detail="Domínio inválido para global.dominio_enum.")
    if slug is not None and not re.fullmatch(r"[a-z0-9-]{1,64}", slug):
        raise HTTPException(status_code=400, detail="Slug inválido. Use [a-z0-9-]{1,64}.")
    if front_ou_back is not None and front_ou_back not in FRONTBACK_ENUM:
        raise HTTPException(status_code=400, detail="front_ou_back inválido (frontend|backend|fullstack).")
    if estado is not None and estado not in ESTADO_ENUM:
        raise HTTPException(status_code=400, detail="estado inválido (producao|beta|dev|desativado).")


# =========================================================
#                         GET
# =========================================================
@router.get(
    "/por-empresa",
    response_model=List[AplicacaoOut],
    summary="Lista aplicações por id_empresa (requer autenticação)",
)
def listar_aplicacoes_por_empresa(
    id_empresa: int = Query(..., gt=0, description="ID da empresa dona das aplicações"),
    current_user: User = Depends(get_current_user),
):
    """
    - Requer autenticação (JWT), mas **não** valida propriedade da empresa.
    - Retorna registros de `global.aplicacoes` com esse `id_empresa`.
    - Não retorna o bytea (`arquivo_zip`).
    """
    with engine.begin() as conn:
        existe = conn.execute(
            text("SELECT 1 FROM global.empresas WHERE id = :id LIMIT 1"),
            {"id": id_empresa},
        ).scalar()

    if not existe:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")

    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    id,
                    dominio::text AS dominio,
                    slug,
                    url_completa,
                    front_ou_back::text AS front_ou_back,
                    estado::text AS estado,
                    id_empresa,
                    precisa_logar
                FROM global.aplicacoes
                WHERE id_empresa = :id_empresa
                ORDER BY id DESC
            """),
            {"id_empresa": id_empresa},
        ).mappings().all()

    return [
        AplicacaoOut(
            id=r["id"],
            dominio=r["dominio"],
            slug=r["slug"],
            url_completa=r["url_completa"],
            front_ou_back=r["front_ou_back"],
            estado=r["estado"],
            id_empresa=r["id_empresa"],
            precisa_logar=bool(r["precisa_logar"]),
        )
        for r in rows
    ]


# =========================================================
#                       POST (criar)
# =========================================================
@router.post("/criar", status_code=status.HTTP_201_CREATED)
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
                    "slug": slug,
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
        if removidos_ids:
            slug_remove = _deploy_slug(slug, estado)
            if slug_remove is not None:
                GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=slug_remove or "")

        if estado in {"producao", "beta", "dev"}:
            slug_deploy = _deploy_slug(slug, estado)
            GitHubPagesDeployer().dispatch(domain=dominio, slug=slug_deploy or "", zip_url=zip_url)
        elif estado is None:
            slug_deploy = _deploy_slug(slug, "producao")
            GitHubPagesDeployer().dispatch(domain=dominio, slug=slug_deploy or "", zip_url=zip_url)
    except Exception as e:
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


# =========================================================
#                PUT ÚNICO (editar geral)
# =========================================================
class EditarAplicacaoBody(BaseModel):
    id: int
    # Campos que podem mexer no deploy
    dominio: Optional[str] = None                  # global.dominio_enum
    slug: Optional[str] = None                     # [a-z0-9-]{1,64} ou None
    estado: Optional[str] = None                   # global.estado_enum
    # Campos só de banco (NÃO disparam deploy)
    front_ou_back: Optional[str] = None            # gestor_capitais.frontbackenum
    id_empresa: Optional[int] = None               # FK empresas.id
    precisa_logar: Optional[bool] = None           # boolean


@router.put(
    "/editar",
    summary="Editar aplicação (PUT unificado). Sempre atualiza o banco; só dispara deploy se mudar (e efetivamente alterar) 'estado', 'dominio' ou 'slug'.",
)
def editar_aplicacao(body: EditarAplicacaoBody, current_user: User = Depends(get_current_user)):
    # 1) Ler registro atual
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT id,
                       dominio::text AS dominio,
                       slug,
                       estado::text AS estado,
                       front_ou_back::text AS front_ou_back,
                       id_empresa,
                       precisa_logar,
                       url_completa,
                       arquivo_zip
                  FROM global.aplicacoes
                 WHERE id = :id
                 LIMIT 1
            """),
            {"id": body.id},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")

    old_dominio       = row["dominio"]
    old_slug          = row["slug"]
    old_estado        = row["estado"]
    old_frontback     = row["front_ou_back"]
    old_id_empresa    = row["id_empresa"]
    old_precisa_logar = row["precisa_logar"]
    old_zip           = row["arquivo_zip"]

    # 2) Normalizar/validar entradas
    # slug: "" -> None
    new_slug = old_slug if body.slug is None else _normalize_slug(body.slug)
    new_dominio    = old_dominio if body.dominio is None else body.dominio
    new_estado     = old_estado if body.estado  is None else body.estado
    new_frontback  = old_frontback if body.front_ou_back is None else body.front_ou_back
    new_id_empresa = old_id_empresa if body.id_empresa is None else body.id_empresa
    new_precisa    = old_precisa_logar if body.precisa_logar is None else body.precisa_logar

    _validate_inputs(new_dominio, new_slug, new_frontback, new_estado)

    # 3) Detectar mudanças relevantes
    changed_dominio = (body.dominio is not None) and (new_dominio != old_dominio)
    changed_slug    = (body.slug    is not None) and (new_slug    != old_slug)
    changed_estado  = (body.estado  is not None) and (new_estado  != old_estado)
    touched_deploy  = changed_dominio or changed_slug or changed_estado

    old_path_active = old_estado in {"producao", "beta", "dev"}
    new_path_active = new_estado in {"producao", "beta", "dev"}

    old_path = _deploy_slug(old_slug, old_estado)
    new_path = _deploy_slug(new_slug, new_estado)

    # 4) Transação de atualização + resolução de conflitos se necessário
    removidos_ids: List[int] = []

    with engine.begin() as conn:
        # 4.1) Se o novo estado for ativo (e vamos mexer nele), garanta exclusividade (dominio,slug,estado)
        if new_path_active and touched_deploy:
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
                {"dom": new_dominio, "slug": new_slug, "est": new_estado, "id": body.id},
            )
            removidos_ids = [r[0] for r in res.fetchall()]

        # 4.2) Atualizar o registro (sempre atualiza, independentemente de deploy)
        nova_url = _canonical_url(new_dominio, new_estado, new_slug)
        conn.execute(
            text("""
                UPDATE global.aplicacoes
                   SET dominio       = CAST(:dominio AS global.dominio_enum),
                       slug          = :slug,
                       estado        = CAST(:estado AS global.estado_enum),
                       front_ou_back = CAST(NULLIF(:fb, '') AS gestor_capitais.frontbackenum),
                       id_empresa    = :id_empresa,
                       precisa_logar = :precisa_logar,
                       url_completa  = :url
                 WHERE id = :id
            """),
            {
                "dominio": new_dominio,
                "slug": new_slug,
                "estado": new_estado,
                "fb": new_frontback or "",
                "id_empresa": new_id_empresa,
                "precisa_logar": new_precisa,
                "url": nova_url,
                "id": body.id,
            },
        )

    # 5) Regras de deploy:
    #    - Só dispara se mudou (e efetivamente alterou) dominio/slug/estado.
    #    - Cenários:
    #       a) ativo -> desativado: remover old_path
    #       b) ativo -> ativo: remover old_path (se path mudou) e publicar new_path
    #       c) desativado -> ativo: publicar new_path
    #       d) desativado -> desativado: nada
    #       e) ativo -> ativo sem path change e sem estado change: nada
    if touched_deploy:
        try:
            # a) remover deploy de conflitos desativados (mesmo estado/URL)
            if removidos_ids and new_path is not None:
                GitHubPagesDeployer().dispatch_delete(domain=new_dominio, slug=new_path or "")

            # b) transições envolvendo o próprio registro
            if old_path_active and not new_path_active:
                # ativo -> desativado
                if old_path is not None:
                    GitHubPagesDeployer().dispatch_delete(domain=old_dominio, slug=old_path or "")

            elif old_path_active and new_path_active:
                # ativo -> ativo
                if (changed_dominio or changed_slug or changed_estado) and (old_path != new_path):
                    # remove o antigo se o caminho mudou
                    if old_path is not None:
                        GitHubPagesDeployer().dispatch_delete(domain=old_dominio, slug=old_path or "")
                    # publica o novo
                    if not BASE_UPLOADS_URL:
                        raise HTTPException(status_code=500, detail="BASE_UPLOADS_URL não configurado.")
                    ts = int(time.time())
                    fname = f"{(new_slug or 'root')}-{body.id}-{ts}.zip"
                    fpath = os.path.join(BASE_UPLOADS_DIR, fname)
                    os.makedirs(BASE_UPLOADS_DIR, exist_ok=True)
                    with open(fpath, "wb") as f:
                        f.write(old_zip)
                    zip_url = f"{BASE_UPLOADS_URL.rstrip('/')}/{fname}"
                    GitHubPagesDeployer().dispatch(domain=new_dominio, slug=new_path or "", zip_url=zip_url)

            elif (not old_path_active) and new_path_active:
                # desativado -> ativo
                if not BASE_UPLOADS_URL:
                    raise HTTPException(status_code=500, detail="BASE_UPLOADS_URL não configurado.")
                ts = int(time.time())
                fname = f"{(new_slug or 'root')}-{body.id}-{ts}.zip"
                fpath = os.path.join(BASE_UPLOADS_DIR, fname)
                os.makedirs(BASE_UPLOADS_DIR, exist_ok=True)
                with open(fpath, "wb") as f:
                    f.write(old_zip)
                zip_url = f"{BASE_UPLOADS_URL.rstrip('/')}/{fname}"
                GitHubPagesDeployer().dispatch(domain=new_dominio, slug=new_path or "", zip_url=zip_url)

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Edição aplicada, mas falha ao processar deploy: {e}",
            )

    return {
        "ok": True,
        "id": body.id,
        "dominio": new_dominio,
        "slug": new_slug,
        "estado": new_estado,
        "id_empresa": new_id_empresa,
        "front_ou_back": new_frontback,
        "precisa_logar": new_precisa,
        "deploy_tocado": touched_deploy,
        "desativados_por_conflito": removidos_ids,
    }


# ======================= DELETE (por id) =======================
class DeleteBody(BaseModel):
    id: int  # deletar por ID, simples


@router.delete(
    "/delete",
    summary="aplicacoes delete (por id)",
    description="Remove o deploy (se estiver no ar) e apaga o registro pelo id.",
)
def aplicacoes_delete(body: DeleteBody, current_user: User = Depends(get_current_user)):
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
