# routers/aplicacoes.py
# -*- coding: utf-8 -*-
import os
import time
import re
import logging
import io
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends, status
from fastapi.responses import StreamingResponse
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

# >>> Base da API que o GitHub Actions deve chamar para atualizar status
API_BASE_FOR_ACTIONS = (
    os.getenv("ACTIONS_API_BASE")
    or os.getenv("API_BASE_FOR_ACTIONS")
    or os.getenv("API_BASE")
)

# Valores válidos (iguais aos ENUMs no Postgres)
DOMINIO_ENUM = {"pinacle.com.br", "gestordecapitais.com", "tetramusic.com.br"}
FRONTBACK_ENUM = {"frontend", "backend", "fullstack"}
ESTADO_ENUM = {"producao", "beta", "dev", "desativado"}
SERVIDOR_ENUM = {"teste 1", "teste 2"}


# =========================================================
#                  MODELS para respostas
# =========================================================
class AplicacaoOut(BaseModel):
    id: int
    dominio: Optional[str] = None
    slug: Optional[str] = None
    url_completa: Optional[str] = None
    front_ou_back: Optional[str] = None
    estado: Optional[str] = None
    id_empresa: Optional[int] = None
    precisa_logar: Optional[bool] = None
    anotacoes: Optional[str] = None
    status: Optional[str] = None
    resumo_do_erro: Optional[str] = None


# ======================= Helpers =======================
def _is_producao(estado: Optional[str]) -> bool:
    return (estado or "producao") == "producao"


def _empresa_segment(conn, id_empresa: Optional[int]) -> Optional[str]:
    if not id_empresa:
        return None
    raw = conn.execute(
        text("SELECT lower(nome) FROM global.empresas WHERE id = :id LIMIT 1"),
        {"id": id_empresa},
    ).scalar()
    if raw is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrado.")

    s = raw.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-")
    return s or None


def _canonical_url(dominio: str, estado: Optional[str], slug: Optional[str], empresa_seg: Optional[str]) -> str:
    base = f"https://{dominio}".rstrip("/")
    parts: List[str] = []
    if estado and not _is_producao(estado):
        parts.append(estado.strip("/"))
    if empresa_seg:
        parts.append(empresa_seg.strip("/"))
    if slug:
        parts.append(slug.strip("/"))
    return base + ("/" + "/".join(parts) if parts else "/")


def _deploy_slug(slug: Optional[str], estado: Optional[str]) -> Optional[str]:
    if not estado or estado == "desativado":
        return None
    if estado == "producao":
        return (slug or "")
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


def _validate_servidor(servidor: Optional[str]):
    if servidor is not None and servidor not in SERVIDOR_ENUM:
        raise HTTPException(status_code=400, detail="servidor inválido (teste 1|teste 2).")


# =========================================================
#                         GET
# =========================================================
@router.get(
    "/por-empresa",
    response_model=List[AplicacaoOut],
    summary="Lista aplicações por id_empresa + globais (requer autenticação)",
)
def listar_aplicacoes_por_empresa(
    id_empresa: int = Query(..., gt=0, description="ID da empresa dona das aplicações"),
    current_user: User = Depends(get_current_user),
):
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
                    a.id,
                    a.dominio::text AS dominio,
                    a.slug,
                    a.url_completa,
                    a.front_ou_back::text AS front_ou_back,
                    a.estado::text AS estado,
                    a.id_empresa,
                    a.precisa_logar,
                    a.anotacoes,
                    a.dados_de_entrada,
                    a.tipos_de_retorno,
                    a.rota,
                    a.porta,
                    a.servidor::text AS servidor,
                    s.status AS status,
                    s.resumo_do_erro AS resumo_do_erro
                FROM global.aplicacoes a
                LEFT JOIN global.status_da_aplicacao s
                  ON s.aplicacao_id = a.id
                WHERE a.id_empresa = :id_empresa
                   OR a.id_empresa IS NULL
                ORDER BY
                    CASE WHEN a.id_empresa = :id_empresa THEN 0 ELSE 1 END,
                    a.id DESC
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
            precisa_logar=None if r["precisa_logar"] is None else bool(r["precisa_logar"]),
            anotacoes=r["anotacoes"],
            status=r["status"],
            resumo_do_erro=r["resumo_do_erro"],
        )
        for r in rows
    ]


# =========================================================
#                 GET /{id}/download  (já existente)
# =========================================================
def _safe_filename(dominio: str, estado: Optional[str], slug: Optional[str], rec_id: int) -> str:
    base = f"{dominio}-{(estado or 'producao')}-{(slug or 'root')}-{rec_id}".strip("-")
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base)
    return f"{base}.zip"


@router.get(
    "/{id}/download",
    summary="Baixa o arquivo_zip da aplicação em formato .zip",
)
def download_zip(
    id: int,
    current_user: User = Depends(get_current_user),
):
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT
                    id,
                    dominio::text AS dominio,
                    slug,
                    estado::text AS estado,
                    arquivo_zip
                FROM global.aplicacoes
                WHERE id = :id
                LIMIT 1
            """),
            {"id": id},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Aplicação não encontrada.")

    data: bytes = row["arquivo_zip"]
    if not data:
        raise HTTPException(status_code=404, detail="Nenhum arquivo associado a esta aplicação.")

    filename = _safe_filename(row["dominio"], row["estado"], row["slug"], row["id"])
    stream = io.BytesIO(data)
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Length": str(len(data)),
    }
    return StreamingResponse(stream, media_type="application/zip", headers=headers)


# =========================================================
#                       POST (criar) — ATUALIZADO
# =========================================================
@router.post("/criar", status_code=status.HTTP_201_CREATED)
async def criar_aplicacao(
    dominio: str = Form(...),
    slug: Optional[str] = Form(None),
    arquivo_zip: UploadFile = File(...),
    front_ou_back: Optional[str] = Form(None),
    estado: Optional[str] = Form(None),
    id_empresa: Optional[int] = Form(None),
    anotacoes: Optional[str] = Form(None),
):
    slug = _normalize_slug(slug)
    front_ou_back = _normalize_slug(front_ou_back)
    estado = _normalize_slug(estado)
    _validate_inputs(dominio, slug, front_ou_back, estado)

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

    db_saved = False
    db_error = None
    new_id: Optional[int] = None
    removidos_ids: List[int] = []
    empresa_seg: Optional[str] = None  # <— garantir escopo fora do try

    try:
        with engine.begin() as conn:
            empresa_seg = _empresa_segment(conn, id_empresa)
            url_full = _canonical_url(dominio, estado, slug, empresa_seg)

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
                        (dominio, slug, arquivo_zip, url_completa, front_ou_back, estado, id_empresa, anotacoes)
                    VALUES
                        (CAST(:dominio AS global.dominio_enum),
                         :slug,
                         :arquivo_zip,
                         :url_completa,
                         CAST(NULLIF(:front_ou_back, '') AS gestor_capitais.frontbackenum),
                         CAST(NULLIF(:estado, '')        AS global.estado_enum),
                         :id_empresa,
                         :anotacoes)
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
                    "anotacoes": anotacoes,
                },
            ).mappings().first()

            new_id = int(row["id"])
            db_saved = True

    except Exception as e:
        db_error = f"{e.__class__.__name__}: {e}"
        logging.getLogger("aplicacoes").warning(
            "Falha ao inserir/substituir em global.aplicacoes: %s", db_error
        )
        url_full = None

    # ➕ Status 'em andamento' (atualizado)
    if db_saved and new_id is not None:
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO global.status_da_aplicacao (aplicacao_id, status, resumo_do_erro)
                        VALUES (:id, 'em andamento', NULL)
                        ON CONFLICT (aplicacao_id) DO UPDATE
                          SET status = 'em andamento',
                              resumo_do_erro = NULL;
                    """),
                    {"id": new_id}
                )
        except Exception as e:
            logging.getLogger("aplicacoes").warning("Falha ao registrar status 'em andamento': %s", e)

    # Disparar deploy/delete
    try:
        if removidos_ids:
            old_path_remove = _deploy_slug(slug, estado)
            if old_path_remove is not None:
                GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=old_path_remove or "")

        estado_efetivo = estado or "producao"
        slug_deploy = _deploy_slug(slug, estado_efetivo)
        if slug_deploy is not None:
            GitHubPagesDeployer().dispatch(
                domain=dominio,
                slug=slug_deploy or "",
                zip_url=zip_url,
                empresa=empresa_seg,
                id_empresa=id_empresa,
                aplicacao_id=new_id,
                api_base=API_BASE_FOR_ACTIONS,
            )
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
#                PUT ÚNICO (editar geral) — ATUALIZADO
# =========================================================
class EditarAplicacaoBody(BaseModel):
    id: int
    dominio: Optional[str] = None
    slug: Optional[str] = None
    estado: Optional[str] = None
    id_empresa: Optional[int] = None
    precisa_logar: Optional[bool] = None


@router.put(
    "/editar",
    summary="Editar aplicação (PUT unificado). Não permite alterar 'front_ou_back'. Deploy segue as regras atuais.",
)
def editar_aplicacao(body: EditarAplicacaoBody, current_user: User = Depends(get_current_user)):
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

    new_slug = old_slug if body.slug is None else _normalize_slug(body.slug)
    new_dominio    = old_dominio if body.dominio is None else body.dominio
    new_estado     = old_estado  if body.estado  is None else body.estado
    new_frontback  = old_frontback
    new_id_empresa = old_id_empresa if body.id_empresa is None else body.id_empresa
    new_precisa    = old_precisa_logar if body.precisa_logar is None else body.precisa_logar

    _validate_inputs(new_dominio, new_slug, new_frontback, new_estado)

    old_path_active = old_estado in {"producao", "beta", "dev"}
    new_path_active = new_estado in {"producao", "beta", "dev"}

    with engine.begin() as conn:
        empresa_seg = _empresa_segment(conn, new_id_empresa)
        nova_url = _canonical_url(new_dominio, new_estado, new_slug, empresa_seg)

        if new_path_active:
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
        else:
            removidos_ids = []

        conn.execute(
            text("""
                UPDATE global.aplicacoes
                   SET dominio       = CAST(:dominio AS global.dominio_enum),
                       slug          = :slug,
                       estado        = CAST(:estado AS global.estado_enum),
                       id_empresa    = :id_empresa,
                       precisa_logar = :precisa_logar,
                       url_completa  = :url
                 WHERE id = :id
            """),
            {
                "dominio": new_dominio,
                "slug": new_slug,
                "estado": new_estado,
                "id_empresa": new_id_empresa,
                "precisa_logar": new_precisa,
                "url": nova_url,
                "id": body.id,
            },
        )

    try:
        if new_path_active:
            old_slug_for_deploy = _deploy_slug(old_slug, old_estado)
            new_slug_for_deploy = _deploy_slug(new_slug, new_estado)

            if old_path_active and old_slug_for_deploy and (old_slug_for_deploy != new_slug_for_deploy):
                GitHubPagesDeployer().dispatch_delete(domain=old_dominio, slug=old_slug_for_deploy or "")

            if not BASE_UPLOADS_URL:
                raise HTTPException(status_code=500, detail="BASE_UPLOADS_URL não configurado.")
            ts = int(time.time())
            fname = f"{(new_slug or 'root')}-{body.id}-{ts}.zip"
            fpath = os.path.join(BASE_UPLOADS_DIR, fname)
            os.makedirs(BASE_UPLOADS_DIR, exist_ok=True)
            with open(fpath, "wb") as f:
                f.write(old_zip)
            zip_url = f"{BASE_UPLOADS_URL.rstrip('/')}/{fname}"

            if removidos_ids and new_slug_for_deploy is not None:
                GitHubPagesDeployer().dispatch_delete(domain=new_dominio, slug=new_slug_for_deploy or "")

            GitHubPagesDeployer().dispatch(
                domain=new_dominio,
                slug=new_slug_for_deploy or "",
                zip_url=zip_url,
                empresa=_empresa_segment  # só para indicar visualmente no diff; valor já usado acima
                    (None, new_id_empresa),
                id_empresa=new_id_empresa,
                aplicacao_id=body.id,
                api_base=API_BASE_FOR_ACTIONS,
            )
        elif (not new_path_active) and old_path_active and (new_estado == "desativado"):
            old_slug_for_deploy = _deploy_slug(old_slug, old_estado)
            if old_slug_for_deploy is not None:
                GitHubPagesDeployer().dispatch_delete(domain=old_dominio, slug=old_slug_for_deploy or "")
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
        "deploy": "feito" if new_path_active else ("delete" if (old_path_active and new_estado == "desativado") else "nenhum"),
        "desativados_por_conflito": removidos_ids,
    }


# ======================= DELETE (por id) — INALTERADO ======================
class DeleteBody(BaseModel):
    id: int


@router.delete(
    "/delete",
    summary="aplicacoes delete (por id)",
    description="Remove o deploy (se estiver no ar) e apaga o registro pelo id.",
)
def aplicacoes_delete(body: DeleteBody, current_user: User = Depends(get_current_user)):
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT id,
                       dominio::text AS dominio,
                       slug,
                       estado::text  AS estado,
                       id_empresa
                FROM global.aplicacoes
                WHERE id = :id
                LIMIT 1
            """),
            {"id": body.id},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")

    dominio = row["dominio"]
    slug = row["slug"]
    estado = row["estado"]

    slug_for_delete = _deploy_slug(slug, estado)

    try:
        if slug_for_delete is not None:
            GitHubPagesDeployer().dispatch_delete(domain=dominio, slug=slug_for_delete or "")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao disparar delete no GitHub: {e}")

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
        "github_action": {"workflow": "delete-landing", "slug_removed": slug_for_delete},
        "apagado_no_banco": apagado_no_banco,
    }


# ========================================================================
#        🔵 NOVO 1) POST /aplicacoes/registrar — SALVA O ZIP NO BANCO
# ========================================================================
@router.post(
    "/registrar",
    status_code=status.HTTP_201_CREATED,
    summary="Registrar aplicação SEM deploy (salva ZIP no bytea e cria status 'preparando')",
)
async def registrar_aplicacao(
    dominio: str = Form(...),
    arquivo_zip: UploadFile = File(...),
    slug: Optional[str] = Form(None),
    front_ou_back: Optional[str] = Form(None),
    estado: Optional[str] = Form(None),
    id_empresa: Optional[int] = Form(None),
    anotacoes: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    slug = _normalize_slug(slug)
    front_ou_back = _normalize_slug(front_ou_back)
    estado = _normalize_slug(estado)
    _validate_inputs(dominio, slug, front_ou_back, estado)

    data = await arquivo_zip.read()
    if not data:
        raise HTTPException(status_code=400, detail="arquivo_zip vazio.")

    with engine.begin() as conn:
        empresa_seg = _empresa_segment(conn, id_empresa)
        url_full = _canonical_url(dominio, estado, slug, empresa_seg)

        # 👇 DESATIVA CONFLITOS EXATAMENTE COMO NO /criar
        if estado in {"producao", "beta", "dev"}:
            conn.execute(
                text("""
                    UPDATE global.aplicacoes
                       SET estado = 'desativado'::global.estado_enum
                     WHERE dominio = CAST(:dom AS global.dominio_enum)
                       AND slug IS NOT DISTINCT FROM :slug
                       AND estado  = CAST(:est AS global.estado_enum)
                """),
                {"dom": dominio, "slug": slug, "est": estado},
            )

        new_id = conn.execute(
            text("""
                INSERT INTO global.aplicacoes
                    (dominio, slug, arquivo_zip, url_completa, front_ou_back, estado, id_empresa, anotacoes)
                VALUES
                    (CAST(:dominio AS global.dominio_enum),
                     :slug,
                     :arquivo_zip,                -- << salva o ZIP no bytea
                     :url_completa,
                     CAST(NULLIF(:front_ou_back, '') AS gestor_capitais.frontbackenum),
                     CAST(NULLIF(:estado, '')        AS global.estado_enum),
                     :id_empresa,
                     :anotacoes)
                RETURNING id
            """),
            {
                "dominio": dominio,
                "slug": slug,
                "arquivo_zip": data,
                "url_completa": url_full,
                "front_ou_back": front_ou_back or "",
                "estado": estado or "",
                "id_empresa": id_empresa,
                "anotacoes": anotacoes,
            },
        ).scalar_one()

        # status = "preparando"
        conn.execute(
            text("""
                INSERT INTO global.status_da_aplicacao (aplicacao_id, status, resumo_do_erro)
                VALUES (:id, 'preparando', NULL)
                ON CONFLICT (aplicacao_id) DO UPDATE
                  SET status = 'preparando',
                      resumo_do_erro = NULL
            """),
            {"id": new_id},
        )

    return {
        "ok": True,
        "id": int(new_id),
        "dominio": dominio,
        "slug": slug,
        "estado": estado,
        "id_empresa": id_empresa,
        "status_inicial": "preparando",
        "url": url_full,
        "front_ou_back": front_ou_back,
        "anotacoes": anotacoes,
    }


# ========================================================================
# 🔵 POST /aplicacoes/{id}/deploy — USA O ZIP DO BANCO + METADADOS
# ========================================================================
@router.post(
    "/{id}/deploy",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Faz o deploy de uma aplicação existente usando o ZIP já salvo no banco (muda status para 'em andamento') e envia rota/idioma de metadados",
)
def deploy_aplicacao_existente(
    id: int,
    meta_rota: str = Query("/", description="Rota dos metadados (ex.: '/', '/contato')"),
    meta_lang: str = Query("pt-BR", description="Lang BCP47 (ex.: 'pt-BR', 'en-US')"),
    current_user: User = Depends(get_current_user),
):
    if not BASE_UPLOADS_URL:
        raise HTTPException(status_code=500, detail="BASE_UPLOADS_URL não configurado.")
    os.makedirs(BASE_UPLOADS_DIR, exist_ok=True)

    meta_rota = (meta_rota or "/").strip() or "/"
    meta_lang = (meta_lang or "pt-BR").strip() or "pt-BR"

    with engine.begin() as conn:
        # ---- carrega app + ZIP do banco
        app_row = conn.execute(
            text("""
                SELECT id,
                       dominio::text AS dominio,
                       slug,
                       estado::text AS estado,
                       id_empresa,
                       arquivo_zip
                  FROM global.aplicacoes
                 WHERE id = :id
                 LIMIT 1
            """),
            {"id": id},
        ).mappings().first()

        if not app_row:
            raise HTTPException(status_code=404, detail="Aplicação não encontrada.")

        data: bytes = app_row["arquivo_zip"]
        if not data:
            raise HTTPException(status_code=400, detail="Aplicação não possui arquivo_zip salvo.")

        dominio = app_row["dominio"]
        slug = app_row["slug"]
        estado = app_row["estado"]
        id_empresa = app_row["id_empresa"]

        # ---- escreve ZIP temporário para ter uma URL pública
        ts = int(time.time())
        fname = f"{(slug or 'root')}-{id}-{ts}.zip"
        fpath = os.path.join(BASE_UPLOADS_DIR, fname)
        with open(fpath, "wb") as f:
            f.write(data)
        zip_url = f"{BASE_UPLOADS_URL.rstrip('/')}/{fname}"

        # ---- garante status 'em andamento'
        conn.execute(
            text("""
                INSERT INTO global.status_da_aplicacao (aplicacao_id, status, resumo_do_erro)
                VALUES (:id, 'em andamento', NULL)
                ON CONFLICT (aplicacao_id) DO UPDATE
                  SET status = 'em andamento',
                      resumo_do_erro = NULL
            """),
            {"id": id},
        )

        # ---- pega id do page_meta correspondente (se existir) para log/telemetria
        page_meta_id = conn.execute(
            text("""
                SELECT id
                  FROM metadados.page_meta
                 WHERE aplicacao_id = :aplicacao_id
                   AND rota = :rota
                   AND lang_tag = :lang
                 LIMIT 1
            """),
            {"aplicacao_id": id, "rota": meta_rota, "lang": meta_lang},
        ).scalar()

        empresa_seg = _empresa_segment(conn, id_empresa)

    estado_efetivo = estado or "producao"
    slug_deploy = _deploy_slug(slug, estado_efetivo)

    # ---- dispara o workflow do GitHub (o workflow buscará os metadados na API)
    try:
        if slug_deploy is not None:
            GitHubPagesDeployer().dispatch(
                domain=dominio,
                slug=slug_deploy or "",
                zip_url=zip_url,
                empresa=empresa_seg,
                id_empresa=id_empresa,
                aplicacao_id=id,
                api_base=API_BASE_FOR_ACTIONS,
                # 🚀 NOVO: parâmetros para o workflow embutir metatags
                meta_rota=meta_rota,
                meta_lang=meta_lang,
                page_meta_id=str(page_meta_id) if page_meta_id else "",
            )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"ZIP lido do banco e status 'em andamento' setado, mas o deploy falhou: {e}",
        )

    return {
        "ok": True,
        "aplicacao_id": id,
        "status_atual": "em andamento",
        "dominio": dominio,
        "slug": slug,
        "estado": estado,
        "zip_url": zip_url,
        "meta_rota": meta_rota,
        "meta_lang": meta_lang,
        "page_meta_id": page_meta_id,
        "mensagem": "Deploy disparado a partir do arquivo salvo no banco (com parâmetros de metadados).",
    }
