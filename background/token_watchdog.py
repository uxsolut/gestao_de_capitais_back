# background/token_watchdog.py
# -*- coding: utf-8 -*-

import asyncio
import json
import secrets
from typing import Optional, Dict, Any, List

import structlog

from config import settings
from database import ProcessamentoRepository
from services.processamento_service import _redis_ordens

logger = structlog.get_logger()

# -------------------------
# Config (com defaults)
# -------------------------
TTL_SECONDS = int(getattr(settings, "TOKEN_TTL_SECONDS", 300))                   # 5 min
REFRESH_THRESHOLD_SEC = int(getattr(settings, "TOKEN_WATCHDOG_REFRESH_THRESHOLD_SECONDS", 90))
GRACE_MS = int(getattr(settings, "TOKEN_WATCHDOG_GRACE_MS", 2000))
INTERVAL_SEC = float(getattr(settings, "TOKEN_WATCHDOG_INTERVAL_SECONDS", 10.0))
NAMESPACE = (getattr(settings, "OPAQUE_TOKEN_NAMESPACE", "tok") or "tok").strip()


def _key_from_db(db_val: Optional[str]) -> Optional[str]:
    if not db_val:
        return None
    s = db_val.strip()
    return s if s.startswith(f"{NAMESPACE}:") else f"{NAMESPACE}:{s}"


def _ensure_payload_v2(payload_str: Optional[str], conta_id: Optional[int]) -> Dict[str, Any]:
    base = {"conta": (str(conta_id) if conta_id is not None else None),
            "requisicao_id": None, "scope": "consulta_reqs", "ordens": []}
    if not payload_str:
        return base
    try:
        p = json.loads(payload_str)
        if isinstance(p, dict):
            p.setdefault("conta", base["conta"])
            p.setdefault("requisicao_id", None)
            p.setdefault("scope", "consulta_reqs")
            p.setdefault("ordens", [])
            return p
    except Exception:
        pass
    return base


# ---- fallbacks para diferenças de nomes no repository -----------------
def _rows_consumidas(repo: ProcessamentoRepository, limit: int = 200) -> List[Dict[str, Any]]:
    for name in ("listar_contas_consumidas_com_token", "listar_ordens_consumidas_com_token"):
        fn = getattr(repo, name, None)
        if callable(fn):
            try:
                return fn(limit=limit)
            except Exception as e:
                logger.warning("watchdog_repo_consumidas_fail", method=name, error=str(e))
    return []


def _rows_inicializadas(repo: ProcessamentoRepository, limit: int = 500) -> List[Dict[str, Any]]:
    for name in ("listar_contas_inicializadas", "listar_ordens_inicializadas"):
        fn = getattr(repo, name, None)
        if callable(fn):
            try:
                return fn(limit=limit)
            except Exception as e:
                logger.warning("watchdog_repo_inicializadas_fail", method=name, error=str(e))
    return []


def _tick_once() -> None:
    repo = ProcessamentoRepository()
    RO = _redis_ordens()

    # 1) Limpar tokens de contas sem nenhuma ordem Inicializado
    consumidas = _rows_consumidas(repo, limit=200)
    logger.info("watchdog_scan_consumidas", qtd=len(consumidas))
    for row in consumidas:
        conta_id = row.get("id")
        key_in_db = _key_from_db(row.get("chave_do_token"))
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

    # 2) Garantir/rotacionar para contas com pelo menos uma ordem Inicializado
    vivas = _rows_inicializadas(repo, limit=500)
    logger.info("watchdog_scan_inicializadas", qtd=len(vivas))
    for row in vivas:
        conta_id = row.get("id")
        db_val = row.get("chave_do_token")
        key = _key_from_db(db_val)

        # a) sem chave no DB -> criar
        if not key:
            payload_v2 = _ensure_payload_v2(None, conta_id)
            new_key = f"{NAMESPACE}:{secrets.token_urlsafe(32)}"
            try:
                RO.set(new_key, json.dumps(payload_v2, ensure_ascii=False), ex=TTL_SECONDS)
                repo.atualizar_chave_token_conta_por_id(conta_id, new_key)
                logger.info("watchdog_token_issued", conta_id=conta_id, key=new_key)
            except Exception as e:
                logger.error("watchdog_issue_error", conta_id=conta_id, error=str(e))
            continue

        # b) já tem chave -> ver TTL
        try:
            ttl = RO.ttl(key)  # -2 não existe, -1 sem TTL, >=0 em segundos
        except Exception as e:
            logger.warning("watchdog_ttl_error", conta_id=conta_id, key=key, error=str(e))
            ttl = -2

        # **CORREÇÃO**: também rotaciona se ttl == -1 (sem TTL)
        precisa_renovar = (ttl in (-2, -1)) or (0 <= ttl <= REFRESH_THRESHOLD_SEC)

        logger.info("watchdog_ttl_check", conta_id=conta_id, key=key, ttl=ttl, acao=("rotacionar" if precisa_renovar else "manter"))
        if not precisa_renovar:
            continue

        # c) obtém payload atual (para preservar ordens)
        try:
            payload_s = RO.get(key)
        except Exception as e:
            logger.warning("watchdog_get_payload_error", conta_id=conta_id, key=key, error=str(e))
            payload_s = None

        payload_v2 = _ensure_payload_v2(payload_s, conta_id)
        new_key = f"{NAMESPACE}:{secrets.token_urlsafe(32)}"

        try:
            pipe = RO.pipeline()
            pipe.set(new_key, json.dumps(payload_v2, ensure_ascii=False), ex=TTL_SECONDS)
            if ttl != -2:
                pipe.pexpire(key, GRACE_MS)  # “período de graça” na chave antiga
            pipe.execute()

            repo.atualizar_chave_token_conta_por_id(conta_id, new_key)
            logger.info("watchdog_token_rotated", conta_id=conta_id, old_key=key, new_key=new_key, old_ttl=ttl)
        except Exception as e:
            logger.error("watchdog_rotate_error", conta_id=conta_id, key=key, error=str(e))


async def _loop() -> None:
    logger.info("token_watchdog_start", interval=INTERVAL_SEC, ttl_seconds=TTL_SECONDS, refresh_threshold=REFRESH_THRESHOLD_SEC)
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
