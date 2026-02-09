# routers/delete.py
# -*- coding: utf-8 -*-
"""
API para apagar/limpar URLs de backend ou frontend.

Recebe uma URL completa (ex: https://pinacle.com.br/testepedro/vinagrete/2/)
e detecta automaticamente se é backend ou frontend, depois apaga tudo.

Suporta:
  - Backends: /miniapi/{nome} → remove systemd service + diretório em /opt/app/api/miniapis/
  - Frontends: /dominio/nome_url/nome/versao → remove diretório em /var/www/pages/
"""
import os
import re
import subprocess
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from database import engine

router = APIRouter(prefix="/delete", tags=["Delete/Cleanup"])

# === Config ===
MINIAPIS_BASE_DIR = os.getenv("MINIAPIS_BASE_DIR", "/opt/app/api/miniapis")
PAGES_DIR = os.getenv("FRONTEND_PAGES_DIR", "/var/www/pages")

# Domínios permitidos
DOMINIOS_PERMITIDOS = [
    "pinacle.com.br",
    "gestordecapitais.com",
    "tetramusic.com.br",
    "grupoaguiarbrasil.com",
]


# =========================================================
#                    MODELOS
# =========================================================
class DeleteRequest(BaseModel):
    """Request para deletar uma URL"""
    url: str


class DeleteResponse(BaseModel):
    """Response após deletar"""
    sucesso: bool
    tipo: str  # "backend" ou "frontend"
    mensagem: str
    detalhes: Optional[dict] = None


# =========================================================
#                    HELPERS
# =========================================================
def _parse_url(url: str) -> dict:
    """
    Parseia URL e extrai componentes.
    
    Suporta:
      - https://pinacle.com.br/testepedro/vinagrete/2/
      - https://pinacle.com.br/testepedro/vinagrete/2
      - https://pinacle.com.br/miniapi/minha-api
    
    Retorna dict com:
      - dominio: str
      - path: str (sem barra inicial)
      - partes: list de path parts
    """
    # Remove barra final se existir
    url = url.rstrip("/")
    
    # Parse URL
    parsed = urlparse(url)
    dominio = parsed.netloc
    path = parsed.path.lstrip("/")
    
    # Split path em partes
    partes = [p for p in path.split("/") if p]
    
    return {
        "dominio": dominio,
        "path": path,
        "partes": partes,
    }


def _is_backend_url(partes: list) -> bool:
    """Detecta se é URL de backend (/miniapi/{nome})"""
    return len(partes) >= 2 and partes[0] == "miniapi"


def _is_frontend_url(partes: list) -> bool:
    """Detecta se é URL de frontend ({nome_url}/{nome}/{versao} ou {nome}/{versao})"""
    # Frontend tem 2-3 partes (nome_url é opcional)
    return len(partes) >= 2 and partes[0] != "miniapi"


def _delete_backend(nome: str) -> dict:
    """
    Deleta backend:
    1. Para systemd service
    2. Remove diretório em /opt/app/api/miniapis/{nome}
    3. Remove Nginx config
    4. Remove entrada do banco de dados
    """
    detalhes = {}
    
    try:
        # 1. Para systemd service
        service_name = f"miniapi-{nome}.service"
        try:
            subprocess.run(
                ["sudo", "systemctl", "stop", service_name],
                capture_output=True,
                timeout=10,
            )
            detalhes["service_stopped"] = True
        except Exception as e:
            detalhes["service_stop_error"] = str(e)
        
        # 2. Desabilita systemd service
        try:
            subprocess.run(
                ["sudo", "systemctl", "disable", service_name],
                capture_output=True,
                timeout=10,
            )
            detalhes["service_disabled"] = True
        except Exception:
            pass
        
        # 3. Remove diretório
        app_dir = os.path.join(MINIAPIS_BASE_DIR, nome)
        if os.path.exists(app_dir):
            try:
                subprocess.run(
                    ["sudo", "rm", "-rf", app_dir],
                    capture_output=True,
                    timeout=30,
                    check=True,
                )
                detalhes["directory_deleted"] = True
            except Exception as e:
                detalhes["directory_delete_error"] = str(e)
        else:
            detalhes["directory_not_found"] = True
        
        # 4. Remove Nginx config
        nginx_conf = f"/etc/nginx/sites-available/miniapi-{nome}.conf"
        if os.path.exists(nginx_conf):
            try:
                subprocess.run(
                    ["sudo", "rm", "-f", nginx_conf],
                    capture_output=True,
                    timeout=10,
                    check=True,
                )
                detalhes["nginx_config_deleted"] = True
            except Exception as e:
                detalhes["nginx_config_delete_error"] = str(e)
        
        # 5. Remove symlink em sites-enabled
        nginx_enabled = f"/etc/nginx/sites-enabled/miniapi-{nome}.conf"
        if os.path.islink(nginx_enabled):
            try:
                subprocess.run(
                    ["sudo", "rm", "-f", nginx_enabled],
                    capture_output=True,
                    timeout=10,
                    check=True,
                )
                detalhes["nginx_enabled_deleted"] = True
            except Exception:
                pass
        
        # 6. Reload Nginx
        try:
            subprocess.run(
                ["sudo", "nginx", "-s", "reload"],
                capture_output=True,
                timeout=10,
            )
            detalhes["nginx_reloaded"] = True
        except Exception as e:
            detalhes["nginx_reload_error"] = str(e)
        
        # 7. Remove do banco de dados
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    DELETE FROM global.aplicacoes
                    WHERE slug = :slug AND front_ou_back = 'backend'
                """), {"slug": nome})
                detalhes["database_deleted"] = True
        except Exception as e:
            detalhes["database_delete_error"] = str(e)
        
        return {
            "sucesso": True,
            "detalhes": detalhes,
        }
    
    except Exception as e:
        return {
            "sucesso": False,
            "erro": str(e),
            "detalhes": detalhes,
        }


def _delete_frontend(dominio: str, nome_url: str, nome: str, versao: str) -> dict:
    """
    Deleta frontend:
    1. Remove diretório em /var/www/pages/{dominio}/{nome_url}/{nome}/{versao}/
    2. Remove entrada do banco de dados
    """
    detalhes = {}
    
    try:
        # Constrói path do frontend
        path_parts = [p for p in [nome_url, nome, versao] if p]
        frontend_dir = os.path.join(PAGES_DIR, dominio, *path_parts)
        
        detalhes["path"] = frontend_dir
        
        # Remove diretório
        if os.path.exists(frontend_dir):
            try:
                subprocess.run(
                    ["sudo", "rm", "-rf", frontend_dir],
                    capture_output=True,
                    timeout=30,
                    check=True,
                )
                detalhes["directory_deleted"] = True
            except Exception as e:
                detalhes["directory_delete_error"] = str(e)
        else:
            detalhes["directory_not_found"] = True
        
        # Remove do banco de dados
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    DELETE FROM global.aplicacoes
                    WHERE slug = :slug AND front_ou_back = 'frontend'
                """), {"slug": nome})
                detalhes["database_deleted"] = True
        except Exception as e:
            detalhes["database_delete_error"] = str(e)
        
        return {
            "sucesso": True,
            "detalhes": detalhes,
        }
    
    except Exception as e:
        return {
            "sucesso": False,
            "erro": str(e),
            "detalhes": detalhes,
        }


# =========================================================
#                    ENDPOINT: POST /
# =========================================================
@router.post("/", response_model=DeleteResponse, status_code=status.HTTP_200_OK,
             summary="Apagar/limpar uma URL (backend ou frontend)")
async def deletar_url(request: DeleteRequest):
    """
    Apaga uma URL completa, detectando automaticamente se é backend ou frontend.
    
    Exemplos:
      - Backend: https://pinacle.com.br/miniapi/minha-api
      - Frontend: https://pinacle.com.br/testepedro/vinagrete/2/
      - Frontend: https://pinacle.com.br/testepedro/vinagrete/2 (sem barra final)
    
    Fluxo:
      1) Parseia URL
      2) Detecta tipo (backend ou frontend)
      3) Apaga tudo relacionado (diretório, systemd, Nginx, banco de dados)
      4) Retorna status
    
    Backend:
      - Para systemd service
      - Remove /opt/app/api/miniapis/{nome}
      - Remove Nginx config
      - Remove do banco
    
    Frontend:
      - Remove /var/www/pages/{dominio}/{nome_url}/{nome}/{versao}/
      - Remove do banco
    """
    
    # Parse URL
    try:
        parsed = _parse_url(request.url)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"URL inválida: {e}"
        )
    
    dominio = parsed["dominio"]
    partes = parsed["partes"]
    
    # Valida domínio
    if dominio not in DOMINIOS_PERMITIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"Domínio '{dominio}' não permitido. Domínios válidos: {', '.join(DOMINIOS_PERMITIDOS)}"
        )
    
    # Detecta tipo
    if _is_backend_url(partes):
        # Backend: /miniapi/{nome}
        nome = partes[1]
        
        # Valida nome
        if not re.match(r"^[a-zA-Z0-9_-]{3,50}$", nome):
            raise HTTPException(
                status_code=400,
                detail="Nome de backend inválido"
            )
        
        # Deleta backend
        result = _delete_backend(nome)
        
        if result["sucesso"]:
            return DeleteResponse(
                sucesso=True,
                tipo="backend",
                mensagem=f"Backend '{nome}' deletado com sucesso",
                detalhes=result.get("detalhes"),
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao deletar backend: {result.get('erro')}"
            )
    
    elif _is_frontend_url(partes):
        # Frontend: {nome_url}/{nome}/{versao} ou {nome}/{versao}
        if len(partes) == 2:
            # {nome}/{versao}
            nome_url = ""
            nome = partes[0]
            versao = partes[1]
        elif len(partes) == 3:
            # {nome_url}/{nome}/{versao}
            nome_url = partes[0]
            nome = partes[1]
            versao = partes[2]
        else:
            raise HTTPException(
                status_code=400,
                detail="Caminho de frontend inválido"
            )
        
        # Deleta frontend
        result = _delete_frontend(dominio, nome_url, nome, versao)
        
        if result["sucesso"]:
            return DeleteResponse(
                sucesso=True,
                tipo="frontend",
                mensagem=f"Frontend '{nome}' deletado com sucesso",
                detalhes=result.get("detalhes"),
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao deletar frontend: {result.get('erro')}"
            )
    
    else:
        raise HTTPException(
            status_code=400,
            detail="URL não reconhecida como backend ou frontend"
        )