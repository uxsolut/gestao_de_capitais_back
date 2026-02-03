# routers/miniapis.py
# -*- coding: utf-8 -*-
import os, io, zipfile, shutil, socket, subprocess, json, re
from datetime import datetime
from typing import Optional, List, Tuple

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

# Host/base para montar a URL pública (ex.: IP 178..., domínio etc.)
FIXED_DEPLOY_DOMAIN = os.getenv("FIXED_DEPLOY_DOMAIN", "pinacle.com.br")
PUBLIC_SCHEME = os.getenv("PUBLIC_SCHEME", "https")  # use "http" p/ IP sem TLS

def _ensure_dirs():
    os.makedirs(BASE_DIR, exist_ok=True)

def _find_free_port() -> int:
    """Encontra uma porta livre no pool configurado"""
    for p in range(PORT_START, PORT_END + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
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
    """Instala dependências do projeto (suporta Python, Node.js, etc)"""
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

def _deploy_root(api_name: str, port: int, route_with_tipo: str, workdir_app: str):
    """
    Chama script de deploy com nome da API
    Passamos a rota COM tipo_api (ex.: /miniapi/minha-api/get)
    para o Nginx publicar exatamente nesse prefixo.
    """
    subprocess.run(["sudo", DEPLOY_BIN, api_name, str(port), route_with_tipo, workdir_app, RUNUSER], check=True)

class MiniApiOut(BaseModel):
    """Modelo de resposta para criação de mini-API"""
    slug: str                # nome da API
    dominio: str
    rota: str                # ex.: "/miniapi/minha-api"
    tipo_api: str            # get|post|put|delete|cron_job|webhook|websocket
    porta: int
    servidor: str
    url_completa: Optional[str] = None

def _as_singleton_list_or_none(raw: Optional[str]) -> Optional[List[str]]:
    """
    Se vier vazio/None -> None (vai para NULL).
    Se vier qualquer texto -> [texto_exato] (um único elemento no array).
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    return [s]

def _insert_backend_row_initial(
    slug: str,               # NOVO: nome único da API
    front_ou_back: Optional[str],
    id_empresa: Optional[int],
    anotacoes: Optional[str],
    dados_de_entrada: Optional[List[str]],
    tipos_de_retorno: Optional[List[str]],
    servidor: Optional[str],
    tipo_api: str,
    arquivo_zip_bytes: bytes,
) -> int:
    """
    Primeiro insert: ainda sem rota/porta/url (pois dependem da porta alocada).
    Já gravamos tipo_api (ENUM) e slug (nome da API).
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
               NULL, :id_empresa, false, :anotacoes,
               :dados, :tipos,
               NULL, NULL, :servidor, CAST(:tipo_api AS "global".tipo_api_enum))
            RETURNING id
        """), {
            "front_ou_back": front_ou_back or "backend",
            "dominio": None,
            "slug": slug,  # NOVO: nome único
            "arquivo_zip": arquivo_zip_bytes,
            "id_empresa": id_empresa,
            "anotacoes": (anotacoes or ""),
            "dados": dados_de_entrada,
            "tipos": tipos_de_retorno,
            "servidor": servidor,
            "tipo_api": tipo_api,
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
             summary="Criar mini-backend (ZIP) e publicar - Aceita qualquer linguagem")
def criar_miniapi(
    arquivo: UploadFile = File(..., description="ZIP com app/main.py (Python) ou equivalente em outra linguagem"),
    # ==== campos vindos do frontend ====
    nome: str = Form(..., description="Nome único da API (3-50 caracteres: letras, números, hífen, underscore)"),
    front_ou_back: Optional[str] = Form(None),     # frontend|backend|fullstack
    id_empresa: Optional[int] = Form(None),
    anotacoes: Optional[str] = Form(None),
    dados_de_entrada: Optional[str] = Form(None, description="Qualquer texto"),
    tipos_de_retorno: Optional[str] = Form(None, description="Qualquer texto"),
    servidor: Optional[str] = Form(None),          # ENUM existente: "teste 1" | "teste 2" | ...
    tipo_api: str = Form(..., description="get|post|put|delete|cron_job|webhook|websocket"),
    # ==== opcional: pode forçar porta; senão aloca automática ====
    porta: Optional[int] = Form(None),
):
    """
    Fluxo:
      1) Valida nome da API (único, formato válido)
      2) INSERT inicial em global.aplicacoes (rota/porta/url NULL; tipo_api preenchido)
      3) Escolhe porta (auto se não vier)
      4) Extrai release, prepara ambiente (suporta Python, Node.js, Java, Go, Rust, etc)
      5) Chama deploy (Nginx + systemd) em /miniapi/{nome}/{tipo_api}/
      6) UPDATE em global.aplicacoes com rota, porta e url_completa
      
    Aceita qualquer tipo de backend:
      - Python: requirements.txt
      - Node.js: package.json
      - Java: pom.xml
      - Go: go.mod
      - Rust: Cargo.toml
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

    # >>> Sem interpretação: salva como veio (um único elemento no array) ou NULL
    dados_list = _as_singleton_list_or_none(dados_de_entrada)
    tipos_list = _as_singleton_list_or_none(tipos_de_retorno)

    # anotacoes independentes
    anotacoes_final = (anotacoes or "").strip()

    # Lê arquivo
    rel_dir = os.path.join(BASE_DIR, "tmp", datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f"))
    os.makedirs(rel_dir, exist_ok=True)
    zip_path = os.path.join(rel_dir, "src.zip")
    zip_bytes = arquivo.file.read()
    _write_bytes(zip_path, zip_bytes)

    # 1) Insert inicial
    new_id = _insert_backend_row_initial(
        slug=nome,  # NOVO: usa nome ao invés de ID
        front_ou_back=front_ou_back,
        id_empresa=id_empresa,
        anotacoes=anotacoes_final,
        dados_de_entrada=dados_list,
        tipos_de_retorno=tipos_list,
        servidor=servidor,
        tipo_api=tipo_api,
        arquivo_zip_bytes=zip_bytes,
    )

    # 2) Rota (com nome da API)
    rota_db = f"/miniapi/{nome}"
    # Rota publicada no Nginx (inclui tipo_api)
    rota_publica = f"/miniapi/{nome}/{tipo_api}"

    # 3) Porta
    if porta is None:
        porta = _find_free_port()

    # 4) Extrai release definitivo e prepara app
    obj_dir = os.path.join(BASE_DIR, nome)  # NOVO: usa nome ao invés de ID
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
        # Não falha se não encontrar - pode ser outro tipo de backend

    _symlink_force(cur_link, release_dir)

    # venv + deps (suporta múltiplas linguagens)
    try:
        _venv_install(app_dir)
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Falha ao instalar dependências: {e}")

    # deploy (systemd + nginx) – com rota incluindo tipo_api
    try:
        _deploy_root(nome, porta, rota_publica, os.path.join(cur_link, "app"))
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Falha no deploy: {e}")

    # 5) Atualiza url completa e campos dinâmicos
    url_comp = f"{PUBLIC_SCHEME}://{FIXED_DEPLOY_DOMAIN}{rota_publica}"
    _update_after_deploy(new_id, rota_db, porta, url_comp)

    return MiniApiOut(
        slug=nome,  # NOVO: retorna nome
        dominio=FIXED_DEPLOY_DOMAIN,
        rota=rota_db,
        tipo_api=tipo_api,
        porta=porta,
        servidor=servidor or "default",
        url_completa=url_comp,
    )