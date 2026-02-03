# routers/miniapis.py
# -*- coding: utf-8 -*-
import os, io, zipfile, shutil, socket, subprocess, json, re
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from database import engine

router = APIRouter(prefix="/miniapis", tags=["Mini APIs"])

# === Config ===
BASE_DIR = os.getenv("MINIAPIS_BASE_DIR", "/opt/app/api/miniapis")
DEPLOY_BIN = os.getenv("MINIAPIS_DEPLOY_BIN", "/usr/local/bin/miniapi-deploy.sh")
RUNUSER = os.getenv("MINIAPIS_RUNUSER", "app")
PORT_START = int(os.getenv("MINIAPIS_PORT_START", "9200"))
PORT_END   = int(os.getenv("MINIAPIS_PORT_END",   "9699"))

# Host/base para montar a URL pública
FIXED_DEPLOY_DOMAIN = "pinacle.com.br"
PUBLIC_SCHEME = "https"

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

def _api_name_exists(name: str) -> bool:
    """Verifica se nome da API já existe no banco"""
    with engine.begin() as conn:
        res = conn.execute(text("""
            SELECT COUNT(*) FROM global.aplicacoes
            WHERE slug = :slug
        """), {"slug": name})
        return res.scalar_one() > 0

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

def _deploy_root(api_name: str, port: int, route: str, workdir_app: str):
    """
    Chama script de deploy com nome da API
    """
    subprocess.run(["sudo", DEPLOY_BIN, api_name, str(port), route, workdir_app, RUNUSER], check=True)

class MiniApiOut(BaseModel):
    """Modelo de resposta para criação de mini-API"""
    slug: str
    dominio: str
    rota: str
    porta: int
    url_completa: Optional[str] = None

def _insert_backend_row_initial(
    slug: str,
    arquivo_zip_bytes: bytes,
) -> int:
    """
    Insert inicial: cria registro com slug e arquivo ZIP
    """
    with engine.begin() as conn:
        res = conn.execute(text("""
            INSERT INTO global.aplicacoes
              (front_ou_back, dominio, slug, arquivo_zip, url_completa,
               estado, id_empresa, precisa_logar, anotacoes,
               dados_de_entrada, tipos_de_retorno,
               rota, porta, servidor, tipo_api)
            VALUES
              (:front_ou_back, :dominio, :slug, :arquivo_zip, NULL,
               NULL, NULL, false, NULL,
               NULL, NULL,
               NULL, NULL, NULL, NULL)
            RETURNING id
        """), {
            "front_ou_back": "backend",
            "dominio": None,
            "slug": slug,
            "arquivo_zip": arquivo_zip_bytes,
        })
        return res.scalar_one()

def _update_after_deploy(id_: int, rota: str, porta: int, url: str):
    """Atualiza rota, porta e URL após deploy bem-sucedido"""
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE global.aplicacoes
               SET rota=:rota, porta=:porta, url_completa=:url
             WHERE id=:id
        """), {"rota": rota, "porta": str(porta), "url": url, "id": id_})

@router.post("/", response_model=MiniApiOut, status_code=status.HTTP_201_CREATED,
             summary="Criar mini-backend (ZIP) e publicar")
def criar_miniapi(
    arquivo: UploadFile = File(..., description="ZIP com app/main.py (Python) ou equivalente em outra linguagem"),
    nome: str = Form(..., description="Nome único da API (3-50 caracteres: letras, números, hífen, underscore)"),
):
    """
    Cria e publica uma mini-API a partir de um arquivo ZIP.
    
    Fluxo:
      1) Valida nome da API (único, formato válido)
      2) INSERT inicial em global.aplicacoes com slug
      3) Aloca porta aleatória (9200-9699)
      4) Extrai release e prepara ambiente (detecta linguagem automaticamente)
      5) Instala dependências (Python/Node.js/Java/Go/Rust)
      6) Faz deploy (Nginx + systemd)
      7) UPDATE com rota, porta e URL
      8) Retorna URL completa para acesso
      
    Aceita qualquer tipo de backend:
      - Python: requirements.txt
      - Node.js: package.json
      - Java: pom.xml
      - Go: go.mod
      - Rust: Cargo.toml
    
    Exemplo de uso:
      curl -X POST "https://pinacle.com.br/pnapi/miniapis/" \\
        -F "arquivo=@api.zip" \\
        -F "nome=minha-api"
    """
    _ensure_dirs()

    # === VALIDAÇÃO DO NOME ===
    if not _validate_api_name(nome):
        raise HTTPException(
            status_code=400,
            detail="Nome inválido. Use 3-50 caracteres: letras, números, hífen, underscore"
        )
    
    if _api_name_exists(nome):
        raise HTTPException(
            status_code=409,
            detail=f"Nome '{nome}' já existe. Escolha outro nome único."
        )

    # Lê arquivo ZIP
    rel_dir = os.path.join(BASE_DIR, "tmp", datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f"))
    os.makedirs(rel_dir, exist_ok=True)
    zip_path = os.path.join(rel_dir, "src.zip")
    zip_bytes = arquivo.file.read()
    _write_bytes(zip_path, zip_bytes)

    # 1) Insert inicial
    new_id = _insert_backend_row_initial(
        slug=nome,
        arquivo_zip_bytes=zip_bytes,
    )

    # 2) Rota SEM /get - apenas /miniapi/{nome}
    rota_db = f"/miniapi/{nome}"

    # 3) Porta aleatória
    porta = _find_free_port()

    # 4) Extrai release definitivo e prepara app
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

    # deploy (systemd + nginx) - passa a rota SEM /get
    try:
        _deploy_root(nome, porta, rota_db, os.path.join(cur_link, "app"))
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Falha no deploy: {e}")

    # 5) Atualiza url completa - SEM /get
    url_comp = f"{PUBLIC_SCHEME}://{FIXED_DEPLOY_DOMAIN}{rota_db}"
    _update_after_deploy(new_id, rota_db, porta, url_comp)

    return MiniApiOut(
        slug=nome,
        dominio=FIXED_DEPLOY_DOMAIN,
        rota=rota_db,
        porta=porta,
        url_completa=url_comp,
    )