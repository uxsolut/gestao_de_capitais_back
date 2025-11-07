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
    # Campos opcionais já existentes na tabela
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
    desvio_caso: Optional[str] = Form(
        None,
        description="Enum global.tipo_de_pagina_enum (login|nao_tem). Opcional.",
    ),
    api_base: Optional[str] = Form(
        None,
        description=(
            "API base que o frontend vai usar (igual ao deploy de frontend normal). "
            "Opcional."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cria uma aplicação FULLSTACK (frontend + backend) e dispara o deploy via Runner:

    - Salva o ZIP completo em global.aplicacoes.arquivo_zip.
    - Marca front_ou_back = 'fullstack'.
    - Dispara o deploy FULLSTACK usando RunnerDeployer.dispatch_fullstack(), que:
        * chama /deploy/fullstack/upload no orquestrador
        * o script deploy_fullstack.sh separa o ZIP em:
            - frontend.zip → deploy_landing.sh (com metadados como no deploy de front normal)
            - backend.zip → miniapi-deploy.sh em /<rota_do_front>/_api/
    """
    # 1) Ler bytes do ZIP enviado
    zip_bytes = await arquivo_zip.read()
    if not zip_bytes:
        raise HTTPException(status_code=400, detail="Arquivo ZIP vazio.")

    # 2) Preparar campos "lista" se vier texto
    def as_singleton_list_or_none(raw: Optional[str]):
        if raw is None:
            return None
        s = raw.strip()
        if not s:
            return None
        return [s]

    dados_list = as_singleton_list_or_none(dados_de_entrada)
    tipos_list = as_singleton_list_or_none(tipos_de_retorno)

    # 3) Criar registro na tabela global.aplicacoes
    app_row = Aplicacao(
        dominio=dominio,
        slug=slug,
        arquivo_zip=zip_bytes,
        url_completa=None,  # poderá ser atualizada depois, se você quiser
        front_ou_back="fullstack",  # força sempre fullstack
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
        desvio_caso=desvio_caso,
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
            api_base=api_base or "",
        )
    except Exception as e:
        # Deploy falhou, mas a aplicação foi criada; devolvemos erro explicando.
        raise HTTPException(
            status_code=500,
            detail=f"Aplicação criada (id={app_row.id}), mas falha ao disparar deploy fullstack: {e}",
        )

    # 6) Retornar a aplicação criada; FastAPI converte para AplicacaoOut
    return app_row
