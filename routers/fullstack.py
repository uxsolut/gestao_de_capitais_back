# routers/fullstack.py
# -*- coding: utf-8 -*-
from datetime import datetime
import os
import re
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    Form,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from models.users import User
from models.aplicacoes import Aplicacao
from schemas.aplicacoes import AplicacaoOut
from services.deploy_adapter import get_deployer
from auth.dependencies import get_current_user

router = APIRouter(prefix="/aplicacoes", tags=["Aplicações Fullstack"])

# >>> Base da API que o GitHub Actions deve chamar para atualizar status
API_BASE_FOR_ACTIONS = (
    os.getenv("ACTIONS_API_BASE")
    or os.getenv("API_BASE_FOR_ACTIONS")
    or os.getenv("API_BASE")
)


# =============================================================================
#                    HELPERS (iguais à lógica de /aplicacoes)
# =============================================================================
def _is_producao(estado: Optional[str]) -> bool:
    return (estado or "producao") == "producao"


def _empresa_segment_sa(db: Session, id_empresa: Optional[int]) -> Optional[str]:
    """
    Versão para usar com Session (igual _empresa_segment do aplicacoes.py,
    só que aproveitando o db já injetado).
    """
    if not id_empresa:
        return None
    raw = db.execute(
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
    """
    Mesmo cálculo de URL do /aplicacoes/criar:
    https://dominio/[estado se != producao]/[empresa_seg]/[slug]
    """
    base = f"https://{dominio}".rstrip("/")
    parts = []
    if estado and not _is_producao(estado):
        parts.append(estado.strip("/"))
    if empresa_seg:
        parts.append(empresa_seg.strip("/"))
    if slug:
        parts.append(slug.strip("/"))
    return base + ("/" + "/".join(parts) if parts else "/")


def _deploy_slug(slug: Optional[str], estado: Optional[str]) -> Optional[str]:
    """
    Mesmo helper usado em /aplicacoes:
    - producao: "<slug>" ou ""
    - beta/dev: "estado/slug" ou "estado"
    - desativado/None: None
    """
    if not estado or estado == "desativado":
        return None
    if estado == "producao":
        return (slug or "")
    return f"{estado}/{slug}" if slug else estado


def _as_singleton_list_or_none(raw: Optional[str]):
    """
    Converte texto em lista [texto] ou None.
    Usado para dados_de_entrada e tipos_de_retorno.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    return [s]


def _criar_aplicacao_model(
    *,
    dominio: str,
    slug: Optional[str],
    zip_bytes: bytes,
    estado: Optional[str],
    id_empresa: Optional[int],
    precisa_logar: bool,
    anotacoes: Optional[str],
    dados_de_entrada: Optional[str],
    tipos_de_retorno: Optional[str],
    servidor: Optional[str],
    url_completa: Optional[str],
) -> Aplicacao:
    """
    Monta o objeto Aplicacao para FULLSTACK (sempre front_ou_back='fullstack'),
    já com url_completa calculada igual ao fluxo de frontend.
    """
    dados_list = _as_singleton_list_or_none(dados_de_entrada)
    tipos_list = _as_singleton_list_or_none(tipos_de_retorno)

    return Aplicacao(
        dominio=dominio,
        slug=slug,
        arquivo_zip=zip_bytes,
        url_completa=url_completa,
        front_ou_back="fullstack",  # sempre fullstack
        estado=estado,
        id_empresa=id_empresa,
        precisa_logar=precisa_logar,
        anotacoes=(anotacoes or ""),
        dados_de_entrada=dados_list,
        tipos_de_retorno=tipos_list,
        rota=None,
        porta=None,
        servidor=servidor,
        tipo_api=None,
        desvio_caso=None,  # não usamos para fullstack
    )


def _desativar_anteriores_mesmo_slug_estado(
    db: Session,
    dominio: str,
    slug: Optional[str],
    estado: Optional[str],
) -> bool:
    """
    Se já existir aplicação com mesmo (dominio, estado, slug),
    marca todas como 'desativado' antes de criar a nova.

    Retorna True se desativou alguma (para sabermos se precisamos
    mandar um dispatch_delete, igual ao /aplicacoes/criar).
    """
    if not slug or not estado:
        return False

    antigos = (
        db.query(Aplicacao)
        .filter(
            Aplicacao.dominio == dominio,
            Aplicacao.slug == slug,
            Aplicacao.estado == estado,
        )
        .all()
    )

    if not antigos:
        return False

    for app in antigos:
        app.estado = "desativado"

    db.flush()
    return True


# ============================================================================
# 1) REGISTRAR FULLSTACK (SEM DEPLOY)
# ============================================================================

@router.post(
    "/fullstack/registrar",
    response_model=AplicacaoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar aplicação FULLSTACK (frontend + backend) SEM disparar deploy",
)
async def registrar_aplicacao_fullstack(
    dominio: str = Form(..., description="Domínio (global.dominio_enum)"),
    slug: Optional[str] = Form(
        None,
        description="Slug minúsculo com hífens (1 a 64 chars), ex.: 'meu-app'",
    ),
    arquivo_zip: UploadFile = File(
        ...,
        description=(
            "ZIP FULLSTACK com duas pastas na raiz: "
            "frontend/ (código do front) e backend/ (código do back FastAPI)."
        ),
    ),
    front_ou_back: Optional[str] = Form(  # mantido só pra compatibilidade com o Swagger
        "fullstack",
        description="Ignorado; será sempre salvo como 'fullstack'.",
    ),
    estado: Optional[str] = Form(
        None,
        description="Enum global.estado_enum (producao|beta|dev|desativado). Opcional.",
    ),
    id_empresa: Optional[int] = Form(None),
    precisa_logar: bool = Form(False),
    anotacoes: Optional[str] = Form(None),
    dados_de_entrada: Optional[str] = Form(
        None,
        description="Texto livre só pra documentação (salvo como lista [texto]).",
    ),
    tipos_de_retorno: Optional[str] = Form(
        None,
        description="Texto livre só pra documentação (salvo como lista [texto]).",
    ),
    servidor: Optional[str] = Form(
        None,
        description="Enum global.servidor_enum (ex.: 'teste 1', 'teste 2'). Opcional.",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Só REGISTRA a aplicação FULLSTACK:

    - Salva o ZIP completo em global.aplicacoes.arquivo_zip.
    - Marca front_ou_back = 'fullstack'.
    - Calcula url_completa igual ao /aplicacoes/criar.
    - NÃO dispara nenhum deploy (nem frontend, nem backend).
    """
    zip_bytes = await arquivo_zip.read()
    if not zip_bytes:
        raise HTTPException(status_code=400, detail="Arquivo ZIP vazio.")

    # Se já existe (dominio, estado, slug), marca os antigos como desativado
    _desativar_anteriores_mesmo_slug_estado(db, dominio, slug, estado)

    # Mesmo cálculo de URL que o fluxo de frontend
    empresa_seg = _empresa_segment_sa(db, id_empresa)
    url_full = _canonical_url(dominio, estado, slug, empresa_seg)

    app_row = _criar_aplicacao_model(
        dominio=dominio,
        slug=slug,
        zip_bytes=zip_bytes,
        estado=estado,
        id_empresa=id_empresa,
        precisa_logar=precisa_logar,
        anotacoes=anotacoes,
        dados_de_entrada=dados_de_entrada,
        tipos_de_retorno=tipos_de_retorno,
        servidor=servidor,
        url_completa=url_full,
    )

    db.add(app_row)
    db.commit()
    db.refresh(app_row)

    return app_row


# ============================================================================
# 2) CRIAR FULLSTACK + DISPARAR DEPLOY IMEDIATO
# ============================================================================

@router.post(
    "/fullstack",
    response_model=AplicacaoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Criar aplicação FULLSTACK (frontend + backend) e disparar deploy",
)
async def criar_aplicacao_fullstack(
    dominio: str = Form(..., description="Domínio (global.dominio_enum)"),
    slug: Optional[str] = Form(
        None,
        description="Slug minúsculo com hífens (1 a 64 chars), ex.: 'meu-app'",
    ),
    arquivo_zip: UploadFile = File(
        ...,
        description=(
            "ZIP FULLSTACK com duas pastas na raiz: "
            "frontend/ (código do front) e backend/ (código do back FastAPI)."
        ),
    ),
    front_ou_back: Optional[str] = Form(
        "fullstack",
        description="Ignorado; será sempre salvo como 'fullstack'.",
    ),
    estado: Optional[str] = Form(
        None,
        description="Enum global.estado_enum (producao|beta|dev|desativado). Opcional.",
    ),
    id_empresa: Optional[int] = Form(None),
    precisa_logar: bool = Form(False),
    anotacoes: Optional[str] = Form(None),
    dados_de_entrada: Optional[str] = Form(
        None,
        description="Texto livre só pra documentação (salvo como lista [texto]).",
    ),
    tipos_de_retorno: Optional[str] = Form(
        None,
        description="Texto livre só pra documentação (salvo como lista [texto]).",
    ),
    servidor: Optional[str] = Form(
        None,
        description="Enum global.servidor_enum (ex.: 'teste 1', 'teste 2'). Opcional.",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cria a aplicação FULLSTACK **e já dispara o deploy** via Runner:

    - Salva o ZIP completo em global.aplicacoes.arquivo_zip.
    - Marca front_ou_back = 'fullstack'.
    - Calcula url_completa igual ao /aplicacoes/criar.
    - Chama RunnerDeployer.dispatch_fullstack(), que:
        * separa o ZIP em frontend.zip e backend.zip
        * frontend → deploy_landing.sh (com metadados, igual deploy de front normal)
        * backend  → publicado em <url_do_front>/_api/
    """
    zip_bytes = await arquivo_zip.read()
    if not zip_bytes:
        raise HTTPException(status_code=400, detail="Arquivo ZIP vazio.")

    # Mesmo comportamento: se já existir (dominio, estado, slug),
    # desativa as anteriores antes de criar a nova.
    tinha_anteriores = _desativar_anteriores_mesmo_slug_estado(db, dominio, slug, estado)

    # 1) Calcular URL completa e slug de deploy (mesma lógica do frontend)
    empresa_seg = _empresa_segment_sa(db, id_empresa)
    url_full = _canonical_url(dominio, estado, slug, empresa_seg)

    estado_efetivo = estado or "producao"
    slug_deploy = _deploy_slug(slug, estado_efetivo)  # isso é o que vai para o deploy

    # 2) Criar registro na tabela global.aplicacoes
    app_row = _criar_aplicacao_model(
        dominio=dominio,
        slug=slug,
        zip_bytes=zip_bytes,
        estado=estado,
        id_empresa=id_empresa,
        precisa_logar=precisa_logar,
        anotacoes=anotacoes,
        dados_de_entrada=dados_de_entrada,
        tipos_de_retorno=tipos_de_retorno,
        servidor=servidor,
        url_completa=url_full,
    )

    db.add(app_row)
    db.commit()
    db.refresh(app_row)

    # 3) Escrever o ZIP em disco para o Runner ler (zip_path)
    base_tmp = "/opt/app/api/fullstack_tmp"
    os.makedirs(base_tmp, exist_ok=True)
    run_dir = os.path.join(
        base_tmp, f"{app_row.id}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S-%f')}"
    )
    os.makedirs(run_dir, exist_ok=True)

    zip_path = os.path.join(run_dir, "release_fullstack.zip")
    with open(zip_path, "wb") as f:
        f.write(zip_bytes)

    # 4) Disparar o deploy FULLSTACK via RunnerDeployer
    deployer = get_deployer()

    try:
        # Se desativou versões anteriores com o mesmo (dominio, estado, slug),
        # manda um delete no path antigo, igual ao /aplicacoes/criar.
        if tinha_anteriores:
            old_path_remove = _deploy_slug(slug, estado)
            if old_path_remove is not None:
                deployer.dispatch_delete(domain=dominio, slug=old_path_remove or "")

        if slug_deploy is not None:
            deployer.dispatch_fullstack(
                domain=dominio,
                slug=slug_deploy or "",
                zip_path=zip_path,
                empresa=empresa_seg,            # mesmo conceito de empresa do /aplicacoes/criar
                id_empresa=id_empresa,
                aplicacao_id=app_row.id,
                api_base=API_BASE_FOR_ACTIONS or "",
            )
    except Exception as e:
        # Deploy falhou, mas a aplicação foi criada; devolvemos erro explicando.
        raise HTTPException(
            status_code=500,
            detail=(
                f"Aplicação criada (id={app_row.id}), "
                f"mas falha ao disparar deploy fullstack: {e}"
            ),
        )

    return app_row
