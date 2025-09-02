# -*- coding: utf-8 -*-
import asyncio
import json
import secrets
from typing import Optional, Dict, Any

import structlog
from config import settings
from database import ProcessamentoRepository
from services.processamento_service import _redis_ordens

logger = structlog.get_logger()

# ------------------------- Config -------------------------
TTL_SECONDS            = int(getattr(settings, "TOKEN_TTL_SECONDS", 300))
REFRESH_THRESHOLD_SEC  = int(getattr(settings, "TOKEN_WATCHDOG_REFRESH_THRESHOLD_SECONDS", 90))
GRACE_MS               = int(getattr(settings, "TOKEN_WATCHDOG_GRACE_MS", 2000))
INTERVAL_SEC           = float(getattr(settings, "TOKEN_WATCHDOG_INTERVAL_SECONDS", 10))
NAMESPACE              = (getattr(settings, "OPAQUE_TOKEN_NAMESPACE", "tok") or "tok").strip()

def _normalize_key(db_val: Optional[str]) -> Optional[str]:
    """Garante prefixo NAMESPACE: ao ler do banco."""
    if not db_val:
        return None
    s = db_val.strip()
    pref = f"{NAMESPACE}:"
    return s if s.startswith(pref) else f"{pref}{s}"

def _ensure_payload_v2(payload_s: Optional[str], conta_id: int) -> Dict[str, Any]:
    """Payload simples por CONTA (sem carregar ordens aqui)."""
    def _sk() -> Dict[str, Any]:
        return {"conta": str(conta_id), "scope": "consulta_reqs", "ordens": []}
    if not payload_s:
        return _sk()
    try:
        p = json.loads(payload_s)
        if isinstance(p, dict) and "ordens" in p:
            p.setdefault("conta", str(conta_id))
            p.setdefault("scope", "consulta_reqs")
            return p
        return _sk()
    except Exception:
        return _sk()

def _issue_new(RO, payload: Dict[str, Any]) -> str:
    raw = secrets.token_urlsafe(32)
    key = f"{NAMESPACE}:{raw}"
    RO.set(key, json.dumps(payload, ensure_ascii=False), ex=TTL_SECONDS)
    return key

def _tick_once() -> None:
    """
    1) Limpa token de CONTAS sem nenhuma ordem 'Inicializado'.
    2) Para CONTAS com 'Inicializado': garante token e rotaciona quando TTL baixo/sumido.
    """
    repo = ProcessamentoRepository()
    RO = _redis_ordens()

    # 1) Contas que podem LIMPAR token (não têm mais 'Inicializado')
    for row in repo.listar_contas_sem_inicializado_com_token(limit=1000):
        conta_id = int(row["id"])
        key_in_db = _normalize_key(row.get("chave_do_token"))
        if key_in_db:
            try:
                RO.delete(key_in_db)
            except Exception as e:
                logger.warning("watchdog_delete_old_key_fail", conta_id=conta_id, key=key_in_db, error=str(e))
        try:
            repo.limpar_chave_token_por_id(conta_id)
            logger.info("watchdog_token_cleared", conta_id=conta_id)
        except Exception as e:
            logger.warning("watchdog_db_clear_fail", conta_id=conta_id, error=str(e))

    # 2) Contas COM ao menos uma ordem 'Inicializado'
    for row in repo.listar_contas_com_inicializado(limit=2000):
        conta_id = int(row["id"])
        db_val = row.get("chave_do_token")
        key = _normalize_key(db_val) if db_val else None

        # Sem chave no DB → emitir
        if not key:
            payload = _ensure_payload_v2(None, conta_id)
            try:
                new_key = _issue_new(RO, payload)
                repo.atualizar_chave_token_conta_por_id(conta_id, new_key)
                logger.info("watchdog_token_issued", conta_id=conta_id, key=new_key)
            except Exception as e:
                logger.error("watchdog_issue_error", conta_id=conta_id, error=str(e))
            continue

        # Já tem chave: checar TTL
        try:
            ttl = RO.ttl(key)  # -2 inexistente, -1 sem TTL, >=0 segundos restantes
        except Exception as e:
            logger.warning("watchdog_ttl_error", conta_id=conta_id, key=key, error=str(e))
            ttl = -2

        precisa_renovar = (ttl == -2) or (ttl == -1) or (0 <= ttl <= REFRESH_THRESHOLD_SEC)
        if not precisa_renovar:
            continue

        # Mantém payload acumulado (se houver)
        try:
            payload_s = RO.get(key)
        except Exception as e:
            logger.warning("watchdog_get_payload_error", conta_id=conta_id, key=key, error=str(e))
            payload_s = None

        payload = _ensure_payload_v2(payload_s, conta_id)

        try:
            new_key = _issue_new(RO, payload)
            pipe = RO.pipeline()
            if ttl != -2:
                pipe.pexpire(key, GRACE_MS)  # pequena janela de graça
            pipe.execute()
            repo.atualizar_chave_token_conta_por_id(conta_id, new_key)
            logger.info("watchdog_token_rotated", conta_id=conta_id, old_key=key, new_key=new_key, old_ttl=ttl)
        except Exception as e:
            logger.error("watchdog_rotate_error", conta_id=conta_id, key=key, error=str(e))

async def _loop() -> None:
    logger.info("token_watchdog_start")
    await asyncio.sleep(0)
    while True:
        try:
            await asyncio.to_thread(_tick_once)
        except Exception as e:
            logger.error("token_watchdog_tick_error", error=str(e))
        await asyncio.sleep(INTERVAL_SEC)

def start_token_watchdog(app) -> None:
    app.state.token_watchdog_task = asyncio.create_task(_loop())

def stop_token_watchdog(app) -> None:
    task = getattr(app.state, "token_watchdog_task", None)
    if task and not task.done():
        task.cancel()
