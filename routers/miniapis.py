# routers/miniapis.py
# -*- coding: utf-8 -*-
import os, io, zipfile, shutil, socket, subprocess, json
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from database import engine
from auth.dependencies import get_current_user
from models.users import User

router = APIRouter(prefix="/miniapis", tags=["Mini APIs"])

# === Config ===
BASE_DIR = os.getenv("MINIAPIS_BASE_DIR", "/opt/app/api/miniapis")
DEPLOY_BIN = os.getenv("MINIAPIS_DEPLOY_BIN", "/usr/local/bin/miniapi-deploy.sh")
RUNUSER = os.getenv("MINIAPIS_RUNUSER", "app")
PORT_START = int(os.getenv("MINIAPIS_PORT_START", "9200"))
PORT_END   = int(os.getenv("MINIAPIS_PORT_END",   "9699"))

# domínio fixo para publicação (ex.: pinacle.com.br ou o IP mostrado na imagem)
FIXED_DEPLOY_DOMAIN = os.getenv("FIXED_DEPLOY_DOMAIN", "pinacle.com.br")

def _ensure_dirs():
    os.makedirs(BASE_DIR, exist_ok=True)

def _find_free_port() -> int:
    for p in range(PORT_START, PORT_END + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("Sem portas livres no pool.")

def _write_bytes(path: str, data: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)

def _unzip_to(src_zip: str, dst_dir: str):
    os.makedirs(dst_dir, exist_ok=True)
    with zipfile.ZipFile(src_zip, "r") as z:
        z.extractall(dst_dir)

def _symlink_force(link: str, target: str):
    if os.path.islink(link) or os.path.exists(link):
        os.unlink(link)
    os.symlink(target, link, target_is_directory=True)

def _venv_install(app_dir: str):
    venv_dir = os.path.join(os.path.dirname(app_dir), ".venv")
    if not os.path.exists(os.path.join(venv_dir, "bin", "python")):
        subprocess.run(["python3", "-m", "venv", venv_dir], check=True)
    pip = os.path.join(venv_dir, "bin", "pip")
    req = os.path.join(app_dir, "requirements.txt")
    if os.path.exists(req):
        subprocess.run([pip, "install", "-r", req], check=True)
    else:
        subprocess.run([pip, "install", "fastapi", "uvicorn"], check=True)

def _deploy_root(id_: int, port: int, route_with_tipo: str, workdir_app: str):
    """
    Mantemos seu script de deploy. Agora passamos a rota já COM tipo_api (ex.: /123/get)
    para o Nginx publicar exatamente nesse prefixo.
    """
    subprocess.run(["sudo", DEPLOY_BIN, str(id_), str(port), route_with_tipo, workdir_app, RUNUSER], check=True)

class MiniApiOut(BaseModel):
    id: int
    dominio: str
    rota: str                # ex.: "/123"
    tipo_api: str            # get|post|put|delete|cron_job|webhook|websocket
    porta: int
    servidor: str
    precisa_logar: bool
    url_completa: Optional[str] = None

def _insert_backend_row_initial(
    dominio: str,
    front_ou_back: Optional[str],
    id_empresa: Optional[int],
    precisa_logar: bool,
    anotacoes: Optional[str],
    dados_de_entrada: Optional[List[str]],
    tipos_de_retorno: Optional[List[str]],
    servidor: Optional[str],
    tipo_api: str,
    arquivo_zip_bytes: bytes,
) -> int:
    """
    Primeiro insert: ainda sem rota/porta/url (pois dependem do ID e da porta alocada).
    Já gravamos tipo_api (ENUM).
    """
    with engine.begin() as conn:
        res = conn.execute(text("""
            INSERT INTO global.aplicacoes
              (front_ou_back, dominio, slug, arquivo_zip, url_completa,
               estado, id_empresa, precisa_logar, anotacoes,
               dados_de_entrada, tipos_de_retorno,
               rota, porta, servidor, tipo_api)
            VALUES
              (:front_ou_back, :dominio, NULL, :arquivo_zip, NULL,
               NULL, :id_empresa, :precisa_logar, :anotacoes,
               :dados, :tipos,
               NULL, NULL, :servidor, :tipo_api::global.tipo_api_enum)
            RETURNING id
        """), {
            "front_ou_back": front_ou_back or "backend",
            "dominio": dominio,
            "arquivo_zip": arquivo_zip_bytes,
            "id_empresa": id_empresa,
            "precisa_logar": precisa_logar,
            "anotacoes": (anotacoes or ""),
            "dados": dados_de_entrada,
            "tipos": tipos_de_retorno,
            "servidor": servidor,
            "tipo_api": tipo_api,
        })
        return res.scalar_one()

def _update_after_deploy(id_: int, rota: str, porta: int, url: str):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE global.aplicacoes
               SET rota=:rota, porta=:porta, url_completa=:url
             WHERE id=:id
        """), {"rota": rota, "porta": str(porta), "url": url, "id": id_})

@router.post("/", response_model=MiniApiOut, status_code=status.HTTP_201_CREATED,
             summary="Criar mini-backend (ZIP) e publicar")
def criar_miniapi(
    arquivo: UploadFile = File(..., description="ZIP com app/main.py (+requirements.txt)"),
    # ==== novos campos vindos do frontend ====
    front_ou_back: Optional[str] = Form(None),     # frontend|backend|fullstack
    id_empresa: Optional[int] = Form(None),
    precisa_logar: bool = Form(False),
    anotacoes: Optional[str] = Form(None),
    dados_de_entrada: Optional[str] = Form(None, description="JSON array (ex.: [\"foo\",\"bar\"])"),
    tipos_de_retorno: Optional[str] = Form(None, description="JSON array"),
    servidor: Optional[str] = Form(None),          # ENUM existente: "teste 1" | "teste 2" | ...
    tipo_api: str = Form(..., description="get|post|put|delete|cron_job|webhook|websocket"),
    # ==== opcional: ainda pode forçar porta, senão aloca automática ====
    porta: Optional[int] = Form(None),
    current_user: User = Depends(get_current_user),
):
    """
    Fluxo:
      1) INSERT inicial em global.aplicacoes (dominio fixo; rota/porta/url NULL; tipo_api preenchido).
      2) Gera ID -> define rota = f"/{id}".
      3) Escolhe porta (auto se não vier).
      4) Extrai release, prepara venv, e chama deploy (Nginx + systemd) em /<id>/<tipo_api>/.
      5) UPDATE em global.aplicacoes com rota, porta e url_completa = https://<dominio>/<id>/<tipo_api>.
    """
    _ensure_dirs()

    # Parse das listas (JSON, se vierem)
    dados_list = json.loads(dados_de_entrada) if dados_de_entrada else None
    tipos_list = json.loads(tipos_de_retorno) if tipos_de_retorno else None

    # Lê arquivo (mantemos também em bytea conforme seu fluxo)
    rel_dir = os.path.join(BASE_DIR, "tmp", datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f"))
    os.makedirs(rel_dir, exist_ok=True)
    zip_path = os.path.join(rel_dir, "src.zip")
    zip_bytes = arquivo.file.read()
    _write_bytes(zip_path, zip_bytes)

    # 1) Insert inicial
    new_id = _insert_backend_row_initial(
        dominio=FIXED_DEPLOY_DOMAIN,
        front_ou_back=front_ou_back,
        id_empresa=id_empresa,
        precisa_logar=precisa_logar,
        anotacoes=anotacoes,
        dados_de_entrada=dados_list,
        tipos_de_retorno=tipos_list,
        servidor=servidor,
        tipo_api=tipo_api,
        arquivo_zip_bytes=zip_bytes,
    )

    # 2) Rota (no DB: apenas "/<id>")
    rota_db = f"/{new_id}"
    # Rota que será publicada no Nginx (inclui tipo_api)
    rota_publica = f"/{new_id}/{tipo_api}"

    # 3) Porta
    if porta is None:
        porta = _find_free_port()

    # 4) Extrai release definitivo e prepara app
    obj_dir = os.path.join(BASE_DIR, str(new_id))
    release_dir = os.path.join(obj_dir, "releases", datetime.utcnow().strftime("%Y%m%d-%H%M%S"))
    cur_link = os.path.join(obj_dir, "current")
    app_dir = os.path.join(release_dir, "app")
    os.makedirs(release_dir, exist_ok=True)

    shutil.move(zip_path, os.path.join(release_dir, "src.zip"))
    _unzip_to(os.path.join(release_dir, "src.zip"), release_dir)

    # Garantir app/main.py (como você já usava)
    main_py = os.path.join(app_dir, "main.py")
    maybe_main = os.path.join(release_dir, "main.py")
    if not os.path.exists(main_py):
        if os.path.exists(maybe_main):
            os.makedirs(app_dir, exist_ok=True)
            shutil.move(maybe_main, main_py)
        else:
            raise HTTPException(400, "ZIP inválido: esperado app/main.py")

    _symlink_force(cur_link, release_dir)

    # venv + deps
    try:
        _venv_install(app_dir)
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Falha ao instalar dependências: {e}")

    # deploy (systemd + nginx include) – agora com a rota incluindo tipo_api
    try:
        _deploy_root(new_id, porta, rota_publica, os.path.join(cur_link, "app"))
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Falha no deploy: {e}")

    # 5) Atualiza url completa e campos dinâmicos
    url_comp = f"https://{FIXED_DEPLOY_DOMAIN}{rota_publica}"
    _update_after_deploy(new_id, rota_db, porta, url_comp)

    return MiniApiOut(
        id=new_id,
        dominio=FIXED_DEPLOY_DOMAIN,
        rota=rota_db,                 # "/<id>"
        tipo_api=tipo_api,            # ENUM
        porta=porta,
        servidor=servidor or "default",
        precisa_logar=precisa_logar,
        url_completa=url_comp,
    )
