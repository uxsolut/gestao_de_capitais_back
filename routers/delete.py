# routers/delete.py
# -*- coding: utf-8 -*-
"""
API para apagar/limpar URLs de backend ou frontend.

Dois endpoints separados:
  - POST /delete/frontend/ → deleta frontend
  - POST /delete/backend/ → deleta backend

CORREÇÃO: Cada URL é independente. Deletar uma URL não afeta outras.
- Frontend: Remove apenas o index.html do diretório especificado
- Backend: Remove apenas o diretório especificado, não afeta outros backends
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
#                    HELPERS - PARSING
# =========================================================
def _parse_url(url: str) -> dict:
    """Parseia URL e extrai componentes"""
    url = url.rstrip("/")
    parsed = urlparse(url)
    dominio = parsed.netloc
    path = parsed.path.lstrip("/")
    partes = [p for p in path.split("/") if p]
    
    return {
        "dominio": dominio,
        "path": path,
        "partes": partes,
    }


# =========================================================
#                    HELPERS - BACKEND
# =========================================================
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


def _delete_backend(nome: str) -> dict:
    """
    Deleta backend ESPECÍFICO:
    1. Para systemd service
    2. Remove APENAS o diretório deste backend
    3. Remove Nginx config
    4. Remove entrada do banco de dados
    
    CORREÇÃO: Remove apenas este backend, não afeta outros!
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
        
        # 3. Remove APENAS o diretório deste backend
        # NÃO remove diretórios pais ou outros backends
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


# =========================================================
#                    HELPERS - FRONTEND
# =========================================================
def _find_frontend_by_path(dominio: str, path_parts: list) -> Optional[dict]:
    """
    Procura por um frontend no filesystem que corresponda EXATAMENTE ao path.
    
    Exemplos:
      - /vinagre/linguamaneiralegalbacana-3-a/14/ → procura em /var/www/pages/gestordecapitais.com/vinagre/linguamaneiralegalbacana-3-a/14/
    
    Retorna dict com {path_completo, partes} se encontrar EXATAMENTE, None caso contrário.
    """
    if not path_parts:
        return None
    
    # Constrói o path completo esperado
    domain_dir = os.path.join(PAGES_DIR, dominio)
    full_path = os.path.join(domain_dir, *path_parts)
    
    # Verifica se existe EXATAMENTE
    if os.path.isdir(full_path):
        return {
            "path_completo": full_path,
            "partes": path_parts,
        }
    
    return None


def _delete_frontend(path_completo: str, partes: list) -> dict:
    """
    Deleta frontend ESPECÍFICO:
    1. Remove APENAS o index.html do diretório especificado
    2. Remove diretório se ficar vazio
    3. Remove entrada do banco de dados
    
    CORREÇÃO: Cada URL é independente!
    - Deletar /vi/banana/ não afeta /vi/banana/na/
    - Deletar /vi/banana/na/ não afeta /vi/banana/
    - Subdirectórios continuam existindo
    """
    detalhes = {}
    
    try:
        detalhes["path"] = path_completo
        
        # 1. Remove APENAS o index.html do diretório especificado
        # NÃO remove subdirectórios
        index_path = os.path.join(path_completo, "index.html")
        if os.path.exists(index_path):
            try:
                subprocess.run(
                    ["sudo", "rm", "-f", index_path],  # Remove APENAS o arquivo
                    capture_output=True,
                    timeout=10,
                    check=True,
                )
                detalhes["index_deleted"] = True
            except Exception as e:
                detalhes["index_delete_error"] = str(e)
        else:
            detalhes["index_not_found"] = True
        
        # 2. Tenta remover o diretório APENAS se estiver vazio
        # Se tiver subdirectórios, deixa intacto
        try:
            os.rmdir(path_completo)  # Remove APENAS se vazio
            detalhes["directory_deleted"] = True
        except OSError:
            # Se não vazio (tem subdirectórios), deixa como está
            detalhes["directory_has_subdirectories"] = True
        
        # 3. Remove do banco de dados (tenta por slug - último part do path)
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
#                    ENDPOINT: DELETE FRONTEND
# =========================================================
@router.post("/frontend/", response_model=DeleteResponse, status_code=status.HTTP_200_OK,
             summary="Apagar/limpar um frontend específico")
async def deletar_frontend(request: DeleteRequest):
    """
    Apaga um frontend ESPECÍFICO a partir de uma URL.
    
    Cada URL é independente. Deletar uma URL não afeta outras.
    
    Exemplo:
      POST /pnapi/delete/frontend/
      {
        "url": "https://pinacle.com.br/testepedro/vinagrete/2/"
      }
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
    
    # Procura por frontend
    frontend_info = _find_frontend_by_path(dominio, path_parts)
    if not frontend_info:
        raise HTTPException(
            status_code=404,
            detail=f"Frontend não encontrado para a URL: {request.url}"
        )
    
    # Deleta frontend
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


# =========================================================
#                    ENDPOINT: DELETE BACKEND
# =========================================================
@router.post("/backend/", response_model=DeleteResponse, status_code=status.HTTP_200_OK,
             summary="Apagar/limpar um backend específico")
async def deletar_backend(request: DeleteRequest):
    """
    Apaga um backend ESPECÍFICO a partir de uma URL.
    
    Cada URL é independente. Deletar uma URL não afeta outras.
    
    Exemplos:
      POST /pnapi/delete/backend/
      {
        "url": "https://pinacle.com.br/miniapi/minha-api"
      }
      
      ou
      
      {
        "url": "https://gestordecapitais.com/vinagre/linguamaneiralegalbacana-3-a/14/"
      }
    """
    
    # Parse URL
    try:
        parsed = _parse_url(request.url)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"URL inválida: {e}"
        )
    
    path_parts = parsed["partes"]
    
    # Procura por backend
    backend_nome = _find_backend_by_path(path_parts)
    if not backend_nome:
        raise HTTPException(
            status_code=404,
            detail=f"Backend não encontrado para a URL: {request.url}"
        )
    
    # Deleta backend
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