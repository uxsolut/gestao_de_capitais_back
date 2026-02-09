# routers/frontends.py
# -*- coding: utf-8 -*-
"""
Deploy de frontends estáticos — sistema independente.

Aceita qualquer ZIP com index.html (HTML, React, Vue, Angular, Flutter pré-compilado, etc.)
e publica em /var/www/pages/{dominio}/{nome_url}/{nome}/{versao}/

Similar ao miniapis.py para backends, mas para frontends estáticos.
"""
import os, zipfile, shutil, subprocess, re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from database import engine

router = APIRouter(prefix="/frontends", tags=["Frontends"])

# === Config ===
DEPLOY_BIN = os.getenv("FRONTEND_DEPLOY_BIN", "/usr/local/bin/frontend-deploy.sh")
PAGES_DIR = os.getenv("FRONTEND_PAGES_DIR", "/var/www/pages")
TMP_DIR = os.getenv("FRONTEND_TMP_DIR", "/tmp/frontend-deploys")
PUBLIC_SCHEME = "https"

# Domínios permitidos (adicione os seus aqui)
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


def _nome_exists(nome: str) -> bool:
    """Verifica se já existe um frontend com esse nome no banco"""
    with engine.begin() as conn:
        res = conn.execute(text("""
            SELECT COUNT(*) FROM global.aplicacoes
            WHERE slug = :slug AND front_ou_back = 'frontend'
        """), {"slug": nome})
        return res.scalar_one() > 0


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
#                    BANCO DE DADOS
# =========================================================
def _insert_frontend_row(
    slug: str,
    dominio: str,
    arquivo_zip_bytes: bytes,
    url_completa: str,
    rota: str,
    nome_url: str,
    versao: str,
) -> int:
    """
    Insert: cria registro do frontend em global.aplicacoes
    """
    with engine.begin() as conn:
        res = conn.execute(text("""
            INSERT INTO global.aplicacoes
              (front_ou_back, dominio, slug, arquivo_zip, url_completa,
               estado, id_empresa, precisa_logar, anotacoes,
               dados_de_entrada, tipos_de_retorno,
               rota, porta, servidor, tipo_api)
            VALUES
              ('frontend',
               CAST(:dominio AS global.dominio_enum),
               :slug, :arquivo_zip, :url_completa,
               'producao'::global.estado_enum, NULL, false, :anotacoes,
               NULL, NULL,
               :rota, NULL, NULL, NULL)
            RETURNING id
        """), {
            "dominio": dominio,
            "slug": slug,
            "arquivo_zip": arquivo_zip_bytes,
            "url_completa": url_completa,
            "rota": rota,
            "anotacoes": f"nome_url={nome_url}, versao={versao}" if (nome_url or versao) else None,
        })
        return res.scalar_one()


def _update_status(app_id: int, status_str: str, erro: str = None):
    """Atualiza status da aplicação"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO global.status_da_aplicacao (aplicacao_id, status, resumo_do_erro)
                VALUES (:id, :status, :erro)
                ON CONFLICT (aplicacao_id) DO UPDATE
                  SET status = :status,
                      resumo_do_erro = :erro
            """), {"id": app_id, "status": status_str, "erro": erro})
    except Exception:
        pass  # Não quebra o deploy por falha de status


# =========================================================
#                    MODELO DE RESPOSTA
# =========================================================
class FrontendOut(BaseModel):
    """Modelo de resposta para criação de frontend"""
    id: int
    slug: str
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
    nome: str = Form(..., description="Nome único do frontend (3-50 caracteres: letras minúsculas, números, hífen)"),
    dominio: str = Form(default="pinacle.com.br", description="Domínio (ex: gestordecapitais.com)"),
    nome_url: str = Form(default="", description="Nome URL (ex: vitor) - opcional"),
    versao: str = Form(default="", description="Versão (ex: 1, v1, 2.0) - opcional"),
):
    """
    Faz deploy de um frontend estático a partir de um arquivo ZIP.

    Fluxo:
      1) Valida parâmetros (nome, domínio, nome_url, versão)
      2) Verifica se nome é único
      3) Salva ZIP temporariamente
      4) INSERT em global.aplicacoes
      5) Chama frontend-deploy.sh (extrai ZIP e publica em /var/www/pages/)
      6) Retorna URL completa para acesso

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

    # Validação de nome único REMOVIDA
    # Agora só importa se a URL completa já existe, não o nome isolado

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

    # === INSERT NO BANCO ===
    try:
        new_id = _insert_frontend_row(
            slug=nome,
            dominio=dominio,
            arquivo_zip_bytes=zip_bytes,
            url_completa=url_completa,
            rota=rota,
            nome_url=nome_url,
            versao=versao,
        )
    except Exception as e:
        # Limpa ZIP temporário
        if os.path.exists(zip_path):
            os.remove(zip_path)
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao salvar no banco: {e}"
        )

    # === STATUS: EM ANDAMENTO ===
    _update_status(new_id, "em andamento")

    # === DEPLOY (chama frontend-deploy.sh) ===
    try:
        result = subprocess.run(
            ["sudo", DEPLOY_BIN, zip_path, dominio, nome_url, nome, versao],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            _update_status(new_id, "falhou", result.stderr or result.stdout)
            raise HTTPException(
                status_code=500,
                detail=f"Deploy falhou: {result.stderr or result.stdout}"
            )
    except subprocess.TimeoutExpired:
        _update_status(new_id, "falhou", "Timeout: deploy demorou mais de 120 segundos")
        raise HTTPException(status_code=500, detail="Deploy timeout (120s)")
    except HTTPException:
        raise
    except Exception as e:
        _update_status(new_id, "falhou", str(e))
        raise HTTPException(status_code=500, detail=f"Falha no deploy: {e}")

    # === STATUS: CONCLUÍDO ===
    _update_status(new_id, "concluído")

    # === LIMPA ZIP TEMPORÁRIO ===
    try:
        if os.path.exists(zip_path):
            os.remove(zip_path)
    except Exception:
        pass

    return FrontendOut(
        id=new_id,
        slug=nome,
        dominio=dominio,
        nome_url=nome_url or "",
        versao=versao or "",
        rota=rota,
        url_completa=url_completa,
    )