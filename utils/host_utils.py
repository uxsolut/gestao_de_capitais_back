# utils/host_utils.py
import re
from fastapi import Request

CANONICO = "gestordecapitais.com"  # ajuste se quiser outro

_ip_regex = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

def extrair_dominio(request: Request) -> str:
    host = (request.headers.get("x-forwarded-host")
            or request.headers.get("host") or "").split(":")[0].lower()
    if _ip_regex.match(host):
        return CANONICO
    return host
