# routers/miniapis.py
# -*- coding: utf-8 -*-
"""
Deploy de mini-APIs — sistema independente, SEM banco de dados.

Aceita ZIP com app/main.py (Python, Node.js, Go, Java, Rust)
e publica em porta aleatória (9200-9699)
"""
import os, io, zipfile, shutil, socket, subprocess, json, re
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from pydantic import BaseModel

router = APIRouter(prefix="/miniapis", tags=["Mini APIs"])

# === Config ===
BASE_DIR = os.getenv("MINIAPIS_BASE_DIR", "/opt/app/api/miniapis")
DEPLOY_BIN = os.getenv("MINIAPIS_DEPLOY_BIN", "/usr/local/bin/miniapi-deploy.sh")
RUNUSER = os.getenv("MINIAPIS_RUNUSER", "app")
PORT_START = int(os.getenv("MINIAPIS_PORT_START", "9200"))
PORT_END   = int(os.getenv("MINIAPIS_PORT_END",   "9699"))

# Host/base para montar a URL pública (domínio padrão)
FIXED_DEPLOY_DOMAIN = "pinacle.com.br"
PUBLIC_SCHEME = "https"

# Lista de domínios permitidos
DOMINIOS_PERMITIDOS = [
    "pinacle.com.br",
    "gestordecapitais.com",
    "tetramusic.com.br",
    "grupoaguiarbrasil.com",
]

def _ensure_dirs():
    """Garante que diretório base existe"""
    os.makedirs(BASE_DIR, exist_ok=True)

def _find_free_port() -> int:
    """Encontra uma porta livre no pool configurado"""
    for p in range(PORT_START, PORT_END + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", p))
                s.close()
                return p
            except OSError:
                continue
    raise RuntimeError("Sem portas livres no pool.")

def _write_bytes(path: str, data: bytes):
    """Escreve bytes em arquivo"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)

def _unzip_to(src_zip: str, dst_dir: str):
    """Extrai arquivo ZIP para diretório"""
    os.makedirs(dst_dir, exist_ok=True)
    with zipfile.ZipFile(src_zip, "r") as z:
        z.extractall(dst_dir)

def _symlink_force(link: str, target: str):
    """Cria symlink, removendo se já existe"""
    if os.path.islink(link) or os.path.exists(link):
        os.unlink(link)
    os.symlink(target, link, target_is_directory=True)

def _validate_api_name(name: str) -> bool:
    """Valida nome da API: apenas letras, números, hífen e underscore"""
    return bool(re.match(r"^[a-zA-Z0-9_-]{3,50}$", name))

def _validate_nome_url(name: str) -> bool:
    """Valida nome_url: apenas letras, números, hífen e underscore (pode ser vazio)"""
    if not name:
        return True
    return bool(re.match(r"^[a-zA-Z0-9_-]{1,50}$", name))

def _validate_versao(versao: str) -> bool:
    """Valida versão: apenas números e pontos (pode ser vazio)"""
    if not versao:
        return True
    return bool(re.match(r"^[a-zA-Z0-9._-]{1,20}$", versao))

def _venv_install(app_dir: str):
    """Instala dependências do projeto (suporta Python, Node.js, Java, Go, Rust)"""
    venv_dir = os.path.join(os.path.dirname(app_dir), ".venv")
    
    # Python
    if os.path.exists(os.path.join(app_dir, "requirements.txt")):
        if not os.path.exists(os.path.join(venv_dir, "bin", "python")):
            subprocess.run(["python3", "-m", "venv", venv_dir], check=True)
        pip = os.path.join(venv_dir, "bin", "pip")
        req = os.path.join(app_dir, "requirements.txt")
        subprocess.run([pip, "install", "-r", req], check=True)
    
    # Node.js
    elif os.path.exists(os.path.join(app_dir, "package.json")):
        subprocess.run(["npm", "install"], cwd=app_dir, check=True)
    
    # Java
    elif os.path.exists(os.path.join(app_dir, "pom.xml")):
        subprocess.run(["mvn", "clean", "package"], cwd=app_dir, check=True)
    
    # Go
    elif os.path.exists(os.path.join(app_dir, "go.mod")):
        subprocess.run(["go", "build"], cwd=app_dir, check=True)
    
    # Rust
    elif os.path.exists(os.path.join(app_dir, "Cargo.toml")):
        subprocess.run(["cargo", "build", "--release"], cwd=app_dir, check=True)
    
    # Fallback: Python padrão
    else:
        if not os.path.exists(os.path.join(venv_dir, "bin", "python")):
            subprocess.run(["python3", "-m", "venv", venv_dir], check=True)
        pip = os.path.join(venv_dir, "bin", "pip")
        subprocess.run([pip, "install", "fastapi", "uvicorn"], check=True)

def _build_url_backend(dominio: str, nome_url: str, nome: str, versao: str) -> str:
    """Constrói a URL pública do backend"""
    parts = [p for p in [nome_url, nome, versao] if p]
    path = "/".join(parts)
    if path:
        return f"{PUBLIC_SCHEME}://{dominio}/{path}"
    else:
        return f"{PUBLIC_SCHEME}://{dominio}"


def _url_exists(dominio: str, nome_url: str, nome: str, versao: str) -> bool:
    """Verifica se a URL já existe no frontend ou backend"""
    # Constrói o path exato que seria criado
    parts = [p for p in [nome_url, nome, versao] if p]
    path_parts = "/".join(parts)
    
    # Procura em /var/www/pages/{dominio}/{path}
    frontend_path = os.path.join("/var/www/pages", dominio, path_parts)
    if os.path.exists(frontend_path):
        return True
    
    # Procura em /opt/app/api/miniapis/{nome}
    backend_path = os.path.join(BASE_DIR, nome)
    if os.path.exists(backend_path):
        return True
    
    return False


def _deploy_root(api_name: str, port: int, route: str, workdir_app: str, dominio: str = "pinacle.com.br"):
    """
    Chama script de deploy com nome da API e domínio customizado
    """
    subprocess.run(["sudo", DEPLOY_BIN, api_name, str(port), route, workdir_app, RUNUSER, dominio], check=True)

class MiniApiOut(BaseModel):
    """Modelo de resposta para criação de mini-API"""
    nome: str
    dominio: str
    rota: str
    porta: int
    url_completa: Optional[str] = None

@router.post("/", response_model=MiniApiOut, status_code=status.HTTP_201_CREATED,
             summary="Criar mini-backend (ZIP) e publicar")
def criar_miniapi(
    arquivo: UploadFile = File(..., description="ZIP com app/main.py (Python) ou equivalente em outra linguagem"),
    nome: str = Form(..., description="Nome da API (3-50 caracteres: letras, números, hífen, underscore)"),
    dominio: str = Form(default="pinacle.com.br", description="Domínio customizado (ex: gestordecapitais.com)"),
    nome_url: str = Form(default="", description="Nome URL (ex: vitor) - opcional"),
    versao: str = Form(default="", description="Versão da API (ex: 1, v1, 2.0) - opcional"),
):
    """
    Cria e publica uma mini-API a partir de um arquivo ZIP.
    
    Fluxo:
      1) Valida nome da API (formato válido)
      2) Aloca porta aleatória (9200-9699)
      3) Extrai release e prepara ambiente (detecta linguagem automaticamente)
      4) Instala dependências (Python/Node.js/Java/Go/Rust)
      5) Faz deploy (Nginx + systemd)
      6) Retorna URL completa para acesso
      
    Aceita qualquer tipo de backend:
      - Python: requirements.txt
      - Node.js: package.json
      - Java: pom.xml
      - Go: go.mod
      - Rust: Cargo.toml
    
    URLs Dinâmicas:
      - Padrão: https://pinacle.com.br/miniapi/{nome}
      - Customizada: https://{dominio}/{nome_url}/{nome}/{versao}
    
    Exemplo de uso (padrão):
      curl -X POST "https://pinacle.com.br/pnapi/miniapis/" \\
        -F "arquivo=@api.zip" \\
        -F "nome=minha-api"
    
    Exemplo de uso (URL customizada):
      curl -X POST "https://pinacle.com.br/pnapi/miniapis/" \\
        -F "arquivo=@api.zip" \\
        -F "nome=apilegal" \\
        -F "dominio=gestordecapitais.com" \\
        -F "nome_url=vitor" \\
        -F "versao=1"
      
      Resultado: https://gestordecapitais.com/vitor/apilegal/1/
    """
    _ensure_dirs()

    # === VALIDAÇÃO DO NOME ===
    if not _validate_api_name(nome):
        raise HTTPException(
            status_code=400,
            detail="Nome inválido. Use 3-50 caracteres: letras, números, hífen, underscore"
        )
    
    # === VALIDAÇÃO DOS PARÂMETROS ===
    if dominio and dominio not in DOMINIOS_PERMITIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"Domínio '{dominio}' não permitido. Domínios válidos: {', '.join(DOMINIOS_PERMITIDOS)}"
        )
    
    if not _validate_nome_url(nome_url):
        raise HTTPException(
            status_code=400,
            detail="Nome URL inválido. Use 1-50 caracteres: letras, números, hífen, underscore"
        )
    
    if not _validate_versao(versao):
        raise HTTPException(
            status_code=400,
            detail="Versão inválida. Use 1-20 caracteres: letras, números, pontos, hífem, underscore"
        )
    
    # Usar domínio customizado ou padrão
    dominio_final = dominio if dominio else FIXED_DEPLOY_DOMAIN
    
    # 1) Construir rota dinamicamente
    if nome_url and versao:
        rota_db = f"/{nome_url}/{nome}/{versao}"
    elif nome_url:
        rota_db = f"/{nome_url}/{nome}"
    elif versao:
        rota_db = f"/miniapi/{nome}/{versao}"
    else:
        rota_db = f"/miniapi/{nome}"
    
    # === VERIFICA SE URL JÁ EXISTE ===
    if _url_exists(dominio_final, nome_url, nome, versao):
        raise HTTPException(
            status_code=409,
            detail=f"URL já existe. Não é possível criar: {_build_url_backend(dominio_final, nome_url, nome, versao)}"
        )

    # Lê arquivo ZIP
    rel_dir = os.path.join(BASE_DIR, "tmp", datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f"))
    os.makedirs(rel_dir, exist_ok=True)
    zip_path = os.path.join(rel_dir, "src.zip")
    zip_bytes = arquivo.file.read()
    _write_bytes(zip_path, zip_bytes)

    # 2) Porta aleatória
    porta = _find_free_port()

    # 3) Extrai release definitivo e prepara app
    obj_dir = os.path.join(BASE_DIR, nome)
    release_dir = os.path.join(obj_dir, "releases", datetime.utcnow().strftime("%Y%m%d-%H%M%S"))
    cur_link = os.path.join(obj_dir, "current")
    app_dir = os.path.join(release_dir, "app")
    os.makedirs(release_dir, exist_ok=True)

    shutil.move(zip_path, os.path.join(release_dir, "src.zip"))
    _unzip_to(os.path.join(release_dir, "src.zip"), release_dir)

    # Garantir app/main.py (Python) ou equivalente
    main_py = os.path.join(app_dir, "main.py")
    maybe_main = os.path.join(release_dir, "main.py")
    if not os.path.exists(main_py):
        if os.path.exists(maybe_main):
            os.makedirs(app_dir, exist_ok=True)
            shutil.move(maybe_main, main_py)

    _symlink_force(cur_link, release_dir)

    # venv + deps
    try:
        _venv_install(app_dir)
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Falha ao instalar dependências: {e}")

    # deploy (systemd + nginx)
    try:
        _deploy_root(nome, porta, rota_db, os.path.join(cur_link, "app"), dominio_final)
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Falha no deploy: {e}")

    # Construir URL completa
    url_comp = f"{PUBLIC_SCHEME}://{dominio_final}{rota_db}"

    return MiniApiOut(
        nome=nome,
        dominio=dominio_final,
        rota=rota_db,
        porta=porta,
        url_completa=url_comp,
    