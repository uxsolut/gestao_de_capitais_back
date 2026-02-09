# routers/delete.py
# -*- coding: utf-8 -*-
"""
API para apagar/limpar URLs de backend ou frontend.

Recebe uma URL completa e procura no servidor se existe algo nela.
Se encontrar, apaga tudo (diretórios, serviços, configs, banco de dados).

Suporta:
  - Backends: procura em /opt/app/api/miniapis/ por qualquer pasta
  - Frontends: procura em /var/www/pages/ por qualquer pasta
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
    tipo: Optional[str] = None  # "backend" ou "frontend"
    mensagem: str
    detalhes: Optional[dict] = None


# =========================================================
#                    HELPERS
# =========================================================
def _parse_url(url: str) -> dict:
    """
    Parseia URL e extrai componentes.
    
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


def _find_backend_by_path(path_parts: list) -> Optional[str]:
    """
    Procura por um backend no filesystem que corresponda ao path.
    
    Exemplos:
      - /miniapi/minha-api → procura por "minha-api" em /opt/app/api/miniapis/
      - /vinagre/linguamaneiralegalbacana-3-a/14/ → procura por "linguamaneiralegalbacana-3-a"
    
    Retorna o nome do backend se encontrar, None caso contrário.
    """
    if not path_parts:
        return None
    
    # Se for /miniapi/{nome}, o nome está em path_parts[1]
    if len(path_parts) >= 2 and path_parts[0] == "miniapi":
        nome = path_parts[1]
        backend_dir = os.path.join(MINIAPIS_BASE_DIR, nome)
        if os.path.isdir(backend_dir):
            return nome
        return None
    
    # Caso contrário, procura em todos os path_parts
    # Tenta encontrar uma pasta em /opt/app/api/miniapis/ que corresponda
    for part in path_parts:
        backend_dir = os.path.join(MINIAPIS_BASE_DIR, part)
        if os.path.isdir(backend_dir):
            return part
    
    return None


def _find_frontend_by_path(dominio: str, path_parts: list) -> Optional[dict]:
    """
    Procura por um frontend no filesystem que corresponda ao path.
    
    Exemplos:
      - /vinagre/linguamaneiralegalbacana-3-a/14/ → procura em /var/www/pages/gestordecapitais.com/vinagre/linguamaneiralegalbacana-3-a/14/
    
    Retorna dict com {path_completo, nome_url, nome, versao} se encontrar, None caso contrário.
    """
    if not path_parts:
        return None
    
    # Tenta construir o path completo
    domain_dir = os.path.join(PAGES_DIR, dominio)
    
    if not os.path.isdir(domain_dir):
        return None
    
    # Tenta o path completo
    full_path = os.path.join(domain_dir, *path_parts)
    if os.path.isdir(full_path):
        return {
            "path_completo": full_path,
            "partes": path_parts,
        }
    
    # Tenta caminhos parciais (em caso de path_parts ter mais níveis)
    for i in range(len(path_parts), 0, -1):
        partial_path = os.path.join(domain_dir, *path_parts[:i])
        if os.path.isdir(partial_path):
            return {
                "path_completo": partial_path,
                "partes": path_parts[:i],
            }
    
    return None


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
        
        # 7. Remove do banco de dados (tenta por slug)
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


def _delete_frontend(path_completo: str, partes: list) -> dict:
    """
    Deleta frontend:
    1. Remove diretório
    2. Remove entrada do banco de dados
    """
    detalhes = {}
    
    try:
        detalhes["path"] = path_completo
        
        # Remove diretório
        if os.path.exists(path_completo):
            try:
                subprocess.run(
                    ["sudo", "rm", "-rf", path_completo],
                    capture_output=True,
                    timeout=30,
                    check=True,
                )
                detalhes["directory_deleted"] = True
            except Exception as e:
                detalhes["directory_delete_error"] = str(e)
        else:
            detalhes["directory_not_found"] = True
        
        # Remove do banco de dados (tenta por slug - último part do path)
        if partes:
            slug = partes[-1]  # Usa o último part como slug
            try:
                with engine.begin() as conn:
                    conn.execute(text("""
                        DELETE FROM global.aplicacoes
                        WHERE slug = :slug AND front_ou_back = 'frontend'
                    """), {"slug": slug})
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
    Apaga uma URL completa, procurando no servidor se existe algo nela.
    
    Exemplos:
      - Backend: https://pinacle.com.br/miniapi/minha-api
      - Backend customizado: https://gestordecapitais.com/vinagre/linguamaneiralegalbacana-3-a/14/
      - Frontend: https://pinacle.com.br/testepedro/vinagrete/2/
    
    Fluxo:
      1) Parseia URL
      2) Procura no filesystem se existe backend ou frontend
      3) Apaga tudo encontrado (diretório, systemd, Nginx, banco de dados)
      4) Retorna status
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
    path_parts = parsed["partes"]
    
    # Valida domínio
    if dominio not in DOMINIOS_PERMITIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"Domínio '{dominio}' não permitido. Domínios válidos: {', '.join(DOMINIOS_PERMITIDOS)}"
        )
    
    # Procura por backend
    backend_nome = _find_backend_by_path(path_parts)
    if backend_nome:
        result = _delete_backend(backend_nome)
        
        if result["sucesso"]:
            return DeleteResponse(
                sucesso=True,
                tipo="backend",
                mensagem=f"Backend '{backend_nome}' deletado com sucesso",
                detalhes=result.get("detalhes"),
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao deletar backend: {result.get('erro')}"
            )
    
    # Procura por frontend
    frontend_info = _find_frontend_by_path(dominio, path_parts)
    if frontend_info:
        result = _delete_frontend(frontend_info["path_completo"], frontend_info["partes"])
        
        if result["sucesso"]:
            return DeleteResponse(
                sucesso=True,
                tipo="frontend",
                mensagem=f"Frontend deletado com sucesso",
                detalhes=result.get("detalhes"),
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao deletar frontend: {result.get('erro')}"
            )
    
    # Nada encontrado
    raise HTTPException(
        status_code=404,
        detail=f"Nenhum backend ou frontend encontrado para a URL: {request.url}"
    )