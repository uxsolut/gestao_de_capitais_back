# routers/fullstack.py
# -*- coding: utf-8 -*-
from datetime import datetime
import os
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

from database import get_db
from models.users import User
from models.aplicacoes import Aplicacao
from schemas.aplicacoes import AplicacaoOut
from services.deploy_adapter import get_deployer
from auth.dependencies import get_current_user

router = APIRouter(prefix="/aplicacoes", tags=["Aplicações Fullstack"])


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
) -> Aplicacao:
    """Monta o objeto Aplicacao para FULLSTACK (sempre front_ou_back='fullstack')."""
    dados_list = _as_singleton_list_or_none(dados_de_entrada)
    tipos_list = _as_singleton_list_or_none(tipos_de_retorno)

    return Aplicacao(
        dominio=dominio,
        slug=slug,
        arquivo_zip=zip_bytes,
        url_completa=None,          # se quiser, depois pode ser atualizada
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
        desvio_caso=None,          # não usamos para fullstack
    )


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
    - NÃO dispara nenhum deploy (nem frontend, nem backend).

    Útil quando você quer primeiro registrar a aplicação, depois ajustar metadados
    no painel de deploy e só então mandar publicar.
    """
    zip_bytes = await arquivo_zip.read()
    if not zip_bytes:
        raise HTTPException(status_code=400, detail="Arquivo ZIP vazio.")

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
    - Chama RunnerDeployer.dispatch_fullstack(), que:
        * separa o ZIP em frontend.zip e backend.zip
        * frontend → deploy_landing.sh (com metadados, igual deploy de front normal)
        * backend  → publicado em <url_do_front>/_api/
    """
    zip_bytes = await arquivo_zip.read()
    if not zip_bytes:
        raise HTTPException(status_code=400, detail="Arquivo ZIP vazio.")

    # 3) Criar registro na tabela global.aplicacoes
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
    )

    db.add(app_row)
    db.commit()
    db.refresh(app_row)

    # 4) Escrever o ZIP em disco para o Runner ler (zip_path)
    base_tmp = "/opt/app/api/fullstack_tmp"
    os.makedirs(base_tmp, exist_ok=True)
    run_dir = os.path.join(
        base_tmp, f"{app_row.id}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S-%f')}"
    )
    os.makedirs(run_dir, exist_ok=True)

    zip_path = os.path.join(run_dir, "release_fullstack.zip")
    with open(zip_path, "wb") as f:
        f.write(zip_bytes)

    # 5) Disparar o deploy FULLSTACK via RunnerDeployer
    deployer = get_deployer()

    try:
        deployer.dispatch_fullstack(
            domain=dominio,
            slug=slug or "",
            zip_path=zip_path,
            empresa=None,            # no futuro dá pra passar nome da empresa aqui
            id_empresa=id_empresa,
            aplicacao_id=app_row.id,
            api_base="",             # backend fica na mesma base do front (/_api/)
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
