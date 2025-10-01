# routers/miniapis.py
# -*- coding: utf-8 -*-
import os, io, zipfile, shutil, socket, subprocess
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

def _deploy_root(id_: int, port: int, route: str, workdir_app: str):
    subprocess.run(["sudo", DEPLOY_BIN, str(id_), str(port), route, workdir_app, RUNUSER], check=True)

class MiniApiOut(BaseModel):
    id: int
    rota: str
    porta: int
    servidor: str
    precisa_logar: bool
    url_completa: Optional[str] = None

def _insert_backend_row(
    dominio: Optional[str],
    rota: str,
    porta: int,
    servidor: str,
    precisa_logar: bool,
    dados_de_entrada: List[str],
    tipos_de_retorno: List[str],
    anotacoes: str,
    arquivo_zip_bytes: Optional[bytes],
    url_completa: Optional[str],
) -> int:
    with engine.connect() as conn:
        res = conn.execute(text("""
            INSERT INTO global.aplicacoes
              (front_ou_back, dominio, slug, arquivo_zip, url_completa,
               estado, id_empresa, precisa_logar, anotacoes,
               dados_de_entrada, tipos_de_retorno,
               rota, porta, servidor)
            VALUES
              ('backend', :dominio, NULL, :arquivo_zip, :url_completa,
               NULL, NULL, :precisa_logar, :anotacoes,
               :dados, :tipos,
               :rota, :porta, :servidor)
            RETURNING id
        """), {
            "dominio": dominio,
            "arquivo_zip": arquivo_zip_bytes,
            "url_completa": url_completa,
            "precisa_logar": precisa_logar,
            "anotacoes": anotacoes,
            "dados": dados_de_entrada,
            "tipos": tipos_de_retorno,
            "rota": rota,
            "porta": porta,
            "servidor": servidor,
        })
        new_id = res.scalar_one()
        conn.commit()
        return new_id

def _update_url_completa(id_: int, url: Optional[str]):
    with engine.connect() as conn:
        conn.execute(text("UPDATE global.aplicacoes SET url_completa=:u WHERE id=:i"),
                     {"u": url, "i": id_})
        conn.commit()

@router.post("/", response_model=MiniApiOut, status_code=status.HTTP_201_CREATED,
             summary="Criar mini-backend (ZIP) e publicar")
def criar_miniapi(
    arquivo: UploadFile = File(..., description="ZIP com app/main.py (+requirements.txt)"),
    rota_base: str = Form(..., description="Ex.: /legal"),
    porta: Optional[int] = Form(None, description="Se vazio, auto (9200-9699)"),
    servidor: str = Form("default"),
    precisa_logar: bool = Form(False),
    dominio: Optional[str] = Form(None, description="Opcional: pinacle.com.br"),
    dados_entrada: Optional[str] = Form(None, description="CSV"),
    tipos_retorno: Optional[str] = Form(None, description="CSV"),
    anotacoes: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    _ensure_dirs()

    rota_base = "/" + rota_base.strip().lstrip("/").rstrip("/")
    if porta is None:
        porta = _find_free_port()

    # listas informativas
    dados_list = [s.strip() for s in (dados_entrada or "").split(",") if s.strip()]
    tipos_list = [s.strip() for s in (tipos_retorno or "").split(",") if s.strip()]

    # salva ZIP no disco para o runtime
    rel_dir = os.path.join(BASE_DIR, "tmp", datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f"))
    zip_path = os.path.join(rel_dir, "src.zip")
    os.makedirs(rel_dir, exist_ok=True)
    zip_bytes = arquivo.file.read()
    _write_bytes(zip_path, zip_bytes)

    # descompacta release definitivo por ID (depois do insert)
    # (montamos um url_completa se tiver dominio)
    url_comp = f"https://{dominio}{rota_base}/" if dominio else None

    # cria linha NA SUA TABELA (sem status extra)
    new_id = _insert_backend_row(
        dominio=dominio,
        rota=rota_base,
        porta=porta,
        servidor=servidor,
        precisa_logar=precisa_logar,
        dados_de_entrada=dados_list,
        tipos_de_retorno=tipos_list,
        anotacoes=anotacoes or "",
        arquivo_zip_bytes=zip_bytes,      # se preferir, troque por NULL para não ocupar DB
        url_completa=url_comp,
    )

    # paths definitivos agora que temos o id
    obj_dir = os.path.join(BASE_DIR, str(new_id))
    release_dir = os.path.join(obj_dir, "releases", datetime.utcnow().strftime("%Y%m%d-%H%M%S"))
    cur_link = os.path.join(obj_dir, "current")
    app_dir = os.path.join(release_dir, "app")
    os.makedirs(release_dir, exist_ok=True)

    # mover o zip temporário e extrair
    shutil.move(zip_path, os.path.join(release_dir, "src.zip"))
    _unzip_to(os.path.join(release_dir, "src.zip"), release_dir)

    # garantir app/main.py (ou tentar mover se veio "reto")
    main_py = os.path.join(app_dir, "main.py")
    maybe_main = os.path.join(release_dir, "main.py")
    if not os.path.exists(main_py):
        if os.path.exists(maybe_main):
            os.makedirs(app_dir, exist_ok=True)
            shutil.move(maybe_main, main_py)
        else:
            raise HTTPException(400, "ZIP inválido: esperado app/main.py")

    # link current -> release
    _symlink_force(cur_link, release_dir)

    # venv + deps
    try:
        _venv_install(app_dir)
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Falha ao instalar dependências: {e}")

    # deploy (systemd + nginx include)
    try:
        _deploy_root(new_id, porta, rota_base, os.path.join(cur_link, "app"))
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Falha no deploy: {e}")

    # opcional: atualizar url_completa se só agora você definiu domínio
    if url_comp:
        _update_url_completa(new_id, url_comp)

    return MiniApiOut(
        id=new_id,
        rota=rota_base,
        porta=porta,
        servidor=servidor,
        precisa_logar=precisa_logar,
        url_completa=url_comp,
    )
