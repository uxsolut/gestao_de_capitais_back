# routers/contatos.py
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from models.contatos import Assinatura, Contato, ContatoCodigo
from schemas.contatos import (
    ContatoCreate,
    ContatoOut,
    ExisteContatoResponse,
    ExisteContatoRequest,
    ValidarCodigoRequest,
    ValidarCodigoResponse,
)
from services.contatos_service import (
    generate_access_code,
    hash_code,
    access_code_expires_at,
    create_contacts_jwt,
    jwt_exp_minutes,
    send_access_code_whatsapp,
)

router = APIRouter(prefix="/api/contatos", tags=["Contatos"])


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


@router.post("", response_model=ContatoOut)
def criar_contato(payload: ContatoCreate, db: Session = Depends(get_db)):
    # valida user existe
    row = db.execute(
        text("SELECT id FROM global.users WHERE id = :id"),
        {"id": int(payload.user_id)},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User não encontrado")

    # valida assinatura existe
    assinatura = db.query(Assinatura).filter(Assinatura.id == int(payload.assinatura_id)).first()
    if not assinatura:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada")

    email_norm = _norm_email(str(payload.email))

    # email único
    ja = db.query(Contato).filter(Contato.email == email_norm).first()
    if ja:
        raise HTTPException(status_code=409, detail="Já existe contato com esse e-mail")

    contato = Contato(
        user_id=int(payload.user_id),
        assinatura_id=int(payload.assinatura_id),
        nome=(payload.nome or "").strip(),
        telefone=(payload.telefone or "").strip(),
        email=email_norm,
        supervisor=False,  # ✅ SEMPRE false automático
    )
    db.add(contato)
    db.commit()
    db.refresh(contato)
    return contato


@router.get("", response_model=list[ContatoOut])
def listar_contatos(
    user_id: int | None = None,
    assinatura_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Contato).order_by(Contato.id.desc())
    if user_id is not None:
        q = q.filter(Contato.user_id == int(user_id))
    if assinatura_id is not None:
        q = q.filter(Contato.assinatura_id == int(assinatura_id))
    return q.all()


@router.delete("/{contato_id}")
def excluir_contato(contato_id: int, db: Session = Depends(get_db)):
    contato = db.query(Contato).filter(Contato.id == int(contato_id)).first()
    if not contato:
        raise HTTPException(status_code=404, detail="Contato não encontrado")

    if contato.supervisor:
        raise HTTPException(status_code=403, detail="Não é permitido excluir contato supervisor")

    db.delete(contato)
    db.commit()
    return {"ok": True}


# -------- Step 1: existe contato + envia código (WhatsApp) --------
@router.get("/existe", response_model=ExisteContatoResponse)
def existe_contato(email: str = Query(...), db: Session = Depends(get_db)):
    email_norm = _norm_email(email)

    contato = db.query(Contato).filter(Contato.email == email_norm).first()
    if not contato:
        return ExisteContatoResponse(exists=False)

    # limpa expirados do contato
    now = datetime.now(timezone.utc)
    expirados = (
        db.query(ContatoCodigo)
        .filter(ContatoCodigo.contato_id == contato.id, ContatoCodigo.expires_at < now)
        .all()
    )
    for item in expirados:
        db.delete(item)
    if expirados:
        db.commit()

    # cria código/desafio
    code = generate_access_code()
    desafio = ContatoCodigo(
        contato_id=contato.id,
        code_hash=hash_code(code),
        expires_at=access_code_expires_at(ttl_minutes=10),
    )
    db.add(desafio)
    db.commit()
    db.refresh(desafio)

    # envia (por enquanto print; depois liga no seu envio real)
    send_access_code_whatsapp(contato.telefone, code)

    # ✅ retorna UUID (não string)
    return ExisteContatoResponse(exists=True, challenge_token=desafio.id, expires_at=desafio.expires_at)


# -------- Step 2: validar código + liberar JWT --------
@router.post("/validar-codigo", response_model=ValidarCodigoResponse)
def validar_codigo(payload: ValidarCodigoRequest, db: Session = Depends(get_db)):
    # garante UUID válido já no parse do pydantic
    challenge_token: UUID = payload.challenge_token

    desafio = db.query(ContatoCodigo).filter(ContatoCodigo.id == challenge_token).first()
    if not desafio:
        raise HTTPException(status_code=404, detail="Challenge inválido")

    now = datetime.now(timezone.utc)
    if now > desafio.expires_at:
        db.delete(desafio)
        db.commit()
        raise HTTPException(status_code=401, detail="Código expirado")

    if hash_code(payload.code) != desafio.code_hash:
        raise HTTPException(status_code=401, detail="Código inválido")

    contato = db.query(Contato).filter(Contato.id == desafio.contato_id).first()
    if not contato:
        db.delete(desafio)
        db.commit()
        raise HTTPException(status_code=404, detail="Contato não encontrado")

    # ✅ validou -> apaga o código
    db.delete(desafio)
    db.commit()

    token = create_contacts_jwt(
        sub=contato.id,  # service já força str()
        extra={
            "email": contato.email,
            "assinatura_id": contato.assinatura_id,
            "supervisor": contato.supervisor,
            "user_id": contato.user_id,
            "tipo": "contato",
        },
    )

    return ValidarCodigoResponse(ok=True, jwt=token, expires_minutes=jwt_exp_minutes())
