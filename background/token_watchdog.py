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

# -------------------------
# Config (com defaults)
# -------------------------
TTL_SECONDS = int(getattr(settings, "TOKEN_TTL_SECONDS", 300))  # TTL do token no Redis (padrão 5 min)
REFRESH_THRESHOLD_SEC = int(getattr(settings, "TOKEN_WATCHDOG_REFRESH_THRESHOLD_SECONDS", 90))  # quando rotacionar
GRACE_MS = int(getattr(settings, "TOKEN_WATCHDOG_GRACE_MS", 2000))  # quanto tempo manter a chave antiga viva
INTERVAL_SEC = float(getattr(settings, "TOKEN_WATCHDOG_INTERVAL_SECONDS", 10))  # intervalo entre ticks
NAMESPACE = (getattr(settings, "OPAQUE_TOKEN_NAMESPACE", "tok") or "tok").strip()


def _key_from_db(db_val: Optional[str]) -> Optional[str]:
    """
    Normaliza para sempre ter o prefixo (ex.: "tok:abc").
    Aceita colunas que já vêm com prefixo ou só o token cru.
    """
    if not db_val:
        return None
    s = db_val.strip()
    return s if s.startswith(f"{NAMESPACE}:") else f"{NAMESPACE}:{s}"


def _ensure_payload_v2(payload_str: Optional[str], conta_id: int) -> Dict[str, Any]:
    """
    Garante payload v2 por CONTA:
      {
        "conta": "<id_conta>",
        "requisicao_id": <int|None>,
        "scope": "consulta_reqs",
        "ordens": [...]
      }
    Se já estiver em v2, normaliza "conta". Se não existir, cria esqueleto.
    """
    def _skeleton() -> Dict[str, Any]:
        return {"conta": str(conta_id), "requisicao_id": None, "scope": "consulta_reqs", "ordens": []}

    if not payload_str:
        return _skeleton()

    try:
        p = json.loads(payload_str)
    except Exception:
        return _skeleton()

    if isinstance(p, dict) and "ordens" in p:
        p["conta"] = str(conta_id)
        p.setdefault("scope", "consulta_reqs")
        p.setdefault("requisicao_id", p.get("requisicao_id"))
        return p

    return _skeleton()


def _tick_once() -> None:
    """
    Passo do watchdog:

      1) Limpa token (Redis + DB) das CONTAS onde NÃO existe nenhuma ordem 'Inicializado'.
      2) Para as CONTAS onde EXISTE ao menos uma 'Inicializado':
         - Gera chave se não existir no DB;
         - Rotaciona se a chave sumiu do Redis, não tem TTL (-1) ou o TTL <= REFRESH_THRESHOLD_SEC.
    """
    repo = ProcessamentoRepository()
    RO = _redis_ordens()

    # 1) Contas que já podem limpar token (todas as ordens != 'Inicializado')
    for row in repo.listar_contas_consumidas_com_token(limit=200):
        conta_id = int(row["id"])
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

    # 2) Contas com pelo menos uma ordem 'Inicializado'
    for row in repo.listar_contas_com_inicializado(limit=500):
        conta_id = int(row["id"])
        key_db_val = row.get("chave_do_token")
        key = _key_from_db(key_db_val) if key_db_val else None

        # Sem chave no banco → emitir uma nova imediatamente
        if not key:
            payload_v2 = _ensure_payload_v2(None, conta_id)
            raw = secrets.token_urlsafe(32)
            new_key = f"{NAMESPACE}:{raw}"
            try:
                RO.set(new_key, json.dumps(payload_v2, ensure_ascii=False), ex=TTL_SECONDS)
                repo.atualizar_chave_token_conta_por_id(conta_id, new_key)
                logger.info("watchdog_token_issued", conta_id=conta_id, key=new_key)
            except Exception as e:
                logger.error("watchdog_issue_error", conta_id=conta_id, error=str(e))
            continue

        # Já tem chave no DB: checar TTL no Redis
        try:
            ttl = RO.ttl(key)  # -2 = não existe | -1 = sem TTL | >=0 = segundos
        except Exception as e:
            logger.warning("watchdog_ttl_error", conta_id=conta_id, key=key, error=str(e))
            ttl = -2

        precisa_renovar = (ttl == -2) or (ttl == -1) or (0 <= ttl <= REFRESH_THRESHOLD_SEC)

        logger.info("watchdog_eval", conta_id=conta_id, key=key, ttl=ttl, renovar=precisa_renovar)

        if not precisa_renovar:
            continue

        # Carrega payload atual (se existir) para não perder as ordens acumuladas
        try:
            payload_s = RO.get(key)
        except Exception as e:
            logger.warning("watchdog_get_payload_error", conta_id=conta_id, key=key, error=str(e))
            payload_s = None

        payload_v2 = _ensure_payload_v2(payload_s, conta_id)

        raw = secrets.token_urlsafe(32)
        new_key = f"{NAMESPACE}:{raw}"

        try:
            pipe = RO.pipeline()
            pipe.set(new_key, json.dumps(payload_v2, ensure_ascii=False), ex=TTL_SECONDS)
            # se a antiga ainda existe, dá um "grace" curto
            if ttl != -2:
                pipe.pexpire(key, GRACE_MS)
            pipe.execute()

            repo.atualizar_chave_token_conta_por_id(conta_id, new_key)
            logger.info("watchdog_token_rotated", conta_id=conta_id, old_key=key, new_key=new_key, old_ttl=ttl)
        except Exception as e:
            logger.error("watchdog_rotate_error", conta_id=conta_id, key=key, error=str(e))


async def _loop() -> None:
    logger.info("token_watchdog_start")
    # deixa o app subir completamente antes do primeiro tick
    await asyncio.sleep(0)
    while True:
        try:
            await asyncio.to_thread(_tick_once)
        except Exception as e:
            logger.error("token_watchdog_tick_error", error=str(e))
        await asyncio.sleep(INTERVAL_SEC)


def start_token_watchdog(app) -> None:
    """
    Inicie o watchdog apenas onde precisa (ex.: serviço 'write').
    Garanta que TOKEN_WATCHDOG_ENABLED esteja = true nesse serviço.
    """
    app.state.token_watchdog_task = asyncio.create_task(_loop())


def stop_token_watchdog(app) -> None:
    task = getattr(app.state, "token_watchdog_task", None)
    if task and not task.done():
        task.cancel()
