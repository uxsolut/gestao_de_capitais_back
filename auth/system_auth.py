from typing import Dict, Any, List
from fastapi import HTTPException, Request, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import json, redis
from config import settings

# Use o MESMO nome que aparece no Swagger: "BearerAuth"
bearer_auth = HTTPBearer(scheme_name="BearerAuth", auto_error=False)

def _redis_global():
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
        db=int(getattr(settings, "REDIS_DB_GLOBAL", 0)),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )

def _ip_in_allowlist(request: Request) -> bool:
    allowlist = getattr(settings, "SYSTEM_IP_ALLOWLIST", "")
    if not allowlist:
        return True
    ips = [ip.strip() for ip in allowlist.split(",") if ip.strip()]
    client_ip = request.client.host if request.client else None
    return (client_ip in ips) if client_ip else False

def get_system_actor(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(bearer_auth),
) -> Dict[str, Any]:
    if not _ip_in_allowlist(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Source IP not allowed.")
    if not credentials or (credentials.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required.")

    token = credentials.credentials
    RG = _redis_global()
    raw = RG.get(f"sys:tok:{token}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired system token.")

    try:
        data = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed system token payload.")

    if data.get("role") != "system":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role.")

    scopes: List[str] = data.get("scopes", [])
    return {
        "role": "system",
        "scopes": scopes,
        "token_id": data.get("token_id"),
        "issued_by": data.get("issued_by"),
        "system_user_id": getattr(settings, "SYSTEM_USER_ID", 1),
    }
