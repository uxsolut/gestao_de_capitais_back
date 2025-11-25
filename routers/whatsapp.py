# routers/whatsapp.py
# -*- coding: utf-8 -*-
import os
from datetime import datetime
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
)
from sqlalchemy.orm import Session

from database import get_db
from models.users import User
from models.whatsapp_envio import WhatsAppEnvio
from schemas.whatsapp_envio import (
    TipoMensagemEnum,
    WhatsAppEnvioResponse,
)

router = APIRouter(
    prefix="/whatsapp",
    tags=["whatsapp"],
)

# pasta onde os arquivos vão ser salvos
UPLOAD_DIR_WHATSAPP = "uploads/whatsapp"
os.makedirs(UPLOAD_DIR_WHATSAPP, exist_ok=True)


@router.post("/enviar", response_model=WhatsAppEnvioResponse)
async def enviar_whatsapp(
    id_user: int = Form(...),
    tipo_user: str = Form(...),
    tipo_mensagem: TipoMensagemEnum = Form(...),
    mensagem: str = Form(...),
    imagem: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """
    Registra um envio de WhatsApp (texto ou imagem) e
    salva a imagem em disco se for o caso.

    Por enquanto:
    - NÃO chama Z-API (modo simulado).
    - Apenas grava na tabela global.whatsapp_envios com status='simulado'.
    """

    # 1) Buscar usuário e telefone
    user = db.query(User).filter(User.id == id_user).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"Usuário {id_user} não encontrado.")

    if not user.telefone:
        raise HTTPException(
            status_code=400,
            detail=f"Usuário {id_user} não possui telefone cadastrado."
        )

    telefone_destino = user.telefone

    # 2) Se for imagem, validar e salvar arquivo
    caminho_imagem: Optional[str] = None

    if tipo_mensagem == TipoMensagemEnum.IMAGEM:
        if imagem is None:
            raise HTTPException(
                status_code=400,
                detail="Para tipo_mensagem='imagem' é obrigatório enviar o arquivo 'imagem'.",
            )

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_name = imagem.filename.replace(" ", "_")
        filename = f"{timestamp}_{safe_name}"
        caminho_imagem = os.path.join(UPLOAD_DIR_WHATSAPP, filename)

        conteudo = await imagem.read()
        with open(caminho_imagem, "wb") as f:
            f.write(conteudo)

    # 3) Criar registro no banco (modo simulado)
    envio = WhatsAppEnvio(
        id_user=id_user,
        tipo_user=tipo_user,
        tipo_mensagem=tipo_mensagem.value,  # salva como string
        telefone_destino=telefone_destino,
        mensagem=mensagem,
        imagem=caminho_imagem,
        status="simulado",
        created_at=datetime.utcnow(),
    )

    db.add(envio)
    db.commit()
    db.refresh(envio)

    # 4) Retorno (Pydantic monta a partir do model)
    return envio
