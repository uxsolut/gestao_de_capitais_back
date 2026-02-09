# routers/frontends.py
# -*- coding: utf-8 -*-
"""
Deploy de frontends estáticos — sistema independente, SEM banco de dados.

Aceita qualquer ZIP com index.html (HTML, React, Vue, Angular, Flutter pré-compilado, etc.)
e publica em /var/www/pages/{dominio}/{nome_url}/{nome}/{versao}/
"""
import os, zipfile, shutil, subprocess, re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from pydantic import BaseModel

router = APIRouter(prefix="/frontends", tags=["Frontends"])

# === Config ===
DEPLOY_BIN = os.getenv("FRONTEND_DEPLOY_BIN", "/usr/local/bin/frontend-deploy.sh")
PAGES_DIR = os.getenv("FRONTEND_PAGES_DIR", "/var/www/pages")
TMP_DIR = os.getenv("FRONTEND_TMP_DIR", "/tmp/frontend-deploys")
PUBLIC_SCHEME = "https"

# Domínios permitidos
DOMINIOS_PERMITIDOS = [
    "pinacle.com.br",
    "gestordecapitais.com",
    "tetramusic.com.br",
    "grupoaguiarbrasil.com",
]


# =========================================================
#                    VALIDAÇÕES
# =========================================================
def _validate_nome(name: str) -> bool:
    """Valida nome: apenas letras minúsculas, números, hífen (3-50 chars)"""
    return bool(re.match(r"^[a-z0-9_-]{3,50}$", name))


def _validate_nome_url(name: str) -> bool:
    """Valida nome_url: apenas letras minúsculas, números, hífen (1-50 chars, pode ser vazio)"""
    if not name:
        return True
    return bool(re.match(r"^[a-z0-9_-]{1,50}$", name))


def _validate_versao(versao: str) -> bool:
    """Valida versão: números, pontos, letras (1-20 chars, pode ser vazio)"""
    if not versao:
        return True
    return bool(re.match(r"^[a-zA-Z0-9._-]{1,20}$", versao))


def _validate_dominio(dominio: str) -> bool:
    """Valida se o domínio está na lista de permitidos"""
    return dominio in DOMINIOS_PERMITIDOS


# =========================================================
#                    HELPERS
# =========================================================
def _build_url(dominio: str, nome_url: str, nome: str, versao: str) -> str:
    """Constrói a URL pública do frontend"""
    parts = [p for p in [nome_url, nome, versao] if p]
    path = "/".join(parts)
    if path:
        return f"{PUBLIC_SCHEME}://{dominio}/{path}"
    else:
        return f"{PUBLIC_SCHEME}://{dominio}"


def _build_rota(nome_url: str, nome: str, versao: str) -> str:
    """Constrói a rota (path) do frontend"""
    parts = [p for p in [nome_url, nome, versao] if p]
    if parts:
        return "/" + "/".join(parts)
    return "/"


def _write_bytes(path: str, data: bytes):
    """Escreve bytes em arquivo"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _validate_zip(zip_bytes: bytes) -> bool:
    """Verifica se o arquivo é um ZIP válido"""
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
            return len(z.namelist()) > 0
    except (zipfile.BadZipFile, Exception):
        return False


# =========================================================
#                    MODELO DE RESPOSTA
# =========================================================
class FrontendOut(BaseModel):
    """Modelo de resposta para criação de frontend"""
    nome: str
    dominio: str
    nome_url: str
    versao: str
    rota: str
    url_completa: str


# =========================================================
#                    ENDPOINT: POST /
# =========================================================
@router.post("/", response_model=FrontendOut, status_code=status.HTTP_201_CREATED,
             summary="Deploy de frontend estático (ZIP) e publicar")
async def criar_frontend(
    arquivo: UploadFile = File(..., description="ZIP com index.html (HTML, React, Vue, Angular, Flutter, etc.)"),
    nome: str = Form(..., description="Nome do frontend (3-50 caracteres: letras minúsculas, números, hífen)"),
    dominio: str = Form(default="pinacle.com.br", description="Domínio (ex: gestordecapitais.com)"),
    nome_url: str = Form(default="", description="Nome URL (ex: vitor) - opcional"),
    versao: str = Form(default="", description="Versão (ex: 1, v1, 2.0) - opcional"),
):
    """
    Faz deploy de um frontend estático a partir de um arquivo ZIP.

    Fluxo:
      1) Valida parâmetros (nome, domínio, nome_url, versão)
      2) Salva ZIP temporariamente
      3) Chama frontend-deploy.sh (extrai ZIP e publica em /var/www/pages/)
      4) Retorna URL completa para acesso

    Aceita qualquer frontend estático:
      - HTML puro (index.html na raiz)
      - React (build/ ou dist/)
      - Vue (dist/)
      - Angular (dist/)
      - Next.js static (out/)
      - Flutter Web (build/web/)
      - Qualquer outro com index.html

    URL gerada: https://{dominio}/{nome_url}/{nome}/{versao}

    Exemplo de uso:
      curl -X POST "https://pinacle.com.br/pnapi/frontends/" \\
        -F "arquivo=@meusite.zip" \\
        -F "nome=meusite" \\
        -F "dominio=gestordecapitais.com" \\
        -F "nome_url=vitor" \\
        -F "versao=1"

      Resultado: https://gestordecapitais.com/vitor/meusite/1
    """

    # === VALIDAÇÕES ===
    if not _validate_nome(nome):
        raise HTTPException(
            status_code=400,
            detail="Nome inválido. Use 3-50 caracteres: letras minúsculas, números, hífen, underscore."
        )

    if not _validate_dominio(dominio):
        raise HTTPException(
            status_code=400,
            detail=f"Domínio '{dominio}' não permitido. Domínios válidos: {', '.join(DOMINIOS_PERMITIDOS)}"
        )

    if not _validate_nome_url(nome_url):
        raise HTTPException(
            status_code=400,
            detail="Nome URL inválido. Use 1-50 caracteres: letras minúsculas, números, hífen, underscore."
        )

    if not _validate_versao(versao):
        raise HTTPException(
            status_code=400,
            detail="Versão inválida. Use 1-20 caracteres: letras, números, pontos, hífen, underscore."
        )

    # === LÊ E VALIDA O ZIP ===
    zip_bytes = await arquivo.read()
    if not zip_bytes:
        raise HTTPException(status_code=400, detail="Arquivo ZIP vazio.")

    if not _validate_zip(zip_bytes):
        raise HTTPException(status_code=400, detail="Arquivo inválido. Envie um ZIP válido.")

    # === CONSTRÓI URL E ROTA ===
    url_completa = _build_url(dominio, nome_url, nome, versao)
    rota = _build_rota(nome_url, nome, versao)

    # === SALVA ZIP TEMPORÁRIO ===
    os.makedirs(TMP_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
    zip_path = os.path.join(TMP_DIR, f"{nome}-{ts}.zip")
    _write_bytes(zip_path, zip_bytes)

    # === DEPLOY (chama frontend-deploy.sh) ===
    try:
        result = subprocess.run(
            ["sudo", DEPLOY_BIN, zip_path, dominio, nome_url, nome, versao],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Deploy falhou: {result.stderr or result.stdout}"
            )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Deploy timeout (120s)")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha no deploy: {e}")

    # === LIMPA ZIP TEMPORÁRIO ===
    try:
        if os.path.exists(zip_path):
            os.remove(zip_path)
    except Exception:
        pass

    return FrontendOut(
        nome=nome,
        dominio=dominio,
        nome_url=nome_url or "",
        versao=versao or "",
        rota=rota,
        url_completa=url_completa,
    )