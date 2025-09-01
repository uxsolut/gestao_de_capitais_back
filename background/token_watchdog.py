# background/token_watchdog.py
# -*- coding: utf-8 -*-

import asyncio
import json
import secrets
from typing import Optional, Dict, Any

import structlog

from config import settings
from database import ProcessamentoRepository
from services.processamento_service import _redis_ordens, _generate_token

logger = structlog.get_logger()

# -------------------------
# Config (com defaults)
# -------------------------
TTL_SECONDS = int(getattr(settings, "TOKEN_TTL_SECONDS", 300))  # TTL do token no Redis
REFRESH_THRESHOLD_SEC = int(getattr(settings, "TOKEN_WATCHDOG_REFRESH_THRESHOLD_SECONDS", 90))  # quando rotacionar
GRACE_MS = int(getattr(settings, "TOKEN_WATCHDOG_GRACE_MS", 2000))  # quanto tempo a chave antiga ainda vive
INTERVAL_SEC = float(getattr(settings, "TOKEN_WATCHDOG_INTERVAL_SECONDS", 10))  # intervalo entre ticks
NAMESPACE = (getattr(settings, "OPAQUE_TOKEN_NAMESPACE", "tok") or "tok").strip()


def _key_from_db(db_val: Optional[str]) -> Optional[str]:
    """
    Garante que a chave tenha o namespace (ex.: "tok:abc").
    Aceita colunas que já vêm com namespace ou só o raw-token.
    """
    if not db_val:
        return None
    s = db_val.strip()
    return s if s.startswith(f"{NAMESPACE}:") else f"{NAMESPACE}:{s}"


def _raw_from_key(key: str) -> str:
    """Extrai a parte 'raw' do token dado 'tok:raw'."""
    pref = f"{NAMESPACE}:"
    return key[len(pref):] if key.startswith(pref) else key


def _ensure_payload_v2(payload_str: Optional[str], conta_id: Optional[int]) -> Dict[str, Any]:
    """
    Garante um payload no formato v2 (somente por CONTA):
      {
        "conta": "<id_conta em string>",
        "requisicao_id": <int|None>,
        "scope": "consulta_reqs",
        "ordens": [ {...}, ... ]
      }
    Se o payload existente já estiver em v2, apenas normaliza "conta".
    Se não houver payload, cria um esqueleto vazio.
    """
    def _skeleton() -> Dict[str, Any]:
        return {
            "conta": str(conta_id) if conta_id is not None else None,
            "requisicao_id": None,   # desconhecido aqui; será atualizado pelo processamento
            "scope": "consulta_reqs",
            "ordens": [],
        }

    if not payload_str:
        return _skeleton()

    try:
        p = json.loads(payload_str)
    except Exception:
        return _skeleton()

    if isinstance(p, dict) and "ordens" in p:
        p["conta"] = str(conta_id) if conta_id is not None else p.get("conta")
        p.setdefault("scope", "consulta_reqs")
        p.setdefault("requisicao_id", p.get("requisicao_id"))
        return p

    # qualquer outro formato -> esqueleto
    return _skeleton()


def _tick_once() -> None:
    """
    Uma passada do watchdog:

      1) Limpa token (DB + Redis) das CONTAS onde NÃO existe nenhuma ordem 'Inicializado'.
      2) Para as CONTAS onde EXISTE ao menos uma 'Inicializado':
         - Gera chave se não existir;
         - Renova/rotaciona se TTL inexistente ou baixo (<= REFRESH_THRESHOLD_SEC).
    """
    repo = ProcessamentoRepository()
    RO = _redis_ordens()

    # 1) Contas onde é seguro limpar (nenhuma ordem 'Inicializado')
    for row in repo.listar_contas_consumidas_com_token(limit=200):
        conta_id = row.get("id")
        key_in_db = _key_from_db(row.get("chave_do_token"))
        if key_in_db:
            try:
                RO.delete(key_in_db)
            except Exception as e:
                logger.warning("watchdog_delete_old_key_fail", key=key_in_db, error=str(e))
        try:
            repo.limpar_chave_token_por_id(conta_id)
            logger.info("watchdog_token_cleared", conta_id=conta_id)
        except Exception as e:
            logger.warning("watchdog_db_clear_fail", conta_id=conta_id, error=str(e))

    # 2) Contas com ordens 'Inicializado' -> garantir/rotacionar chave
    for row in repo.listar_ordens_inicializadas(limit=500):
        conta_id = row.get("id")  # ID da conta
        db_val = row.get("chave_do_token")
        key = _key_from_db(db_val)

        # Sem chave no banco → criar
        if not key:
            payload_v2 = _ensure_payload_v2(None, conta_id)
            raw = _generate_token() if callable(_generate_token) else secrets.token_urlsafe(32)
            new_key = f"{NAMESPACE}:{raw}"
            try:
                RO.set(new_key, json.dumps(payload_v2, ensure_ascii=False), ex=TTL_SECONDS)
                repo.atualizar_chave_token_conta_por_id(conta_id, new_key)
                logger.info("watchdog_token_issued", conta_id=conta_id, key=new_key)
            except Exception as e:
                logger.error("watchdog_issue_error", conta_id=conta_id, error=str(e))
            continue

        # Já tem chave: ver TTL e renovar quando necessário
        try:
            ttl = RO.ttl(key)  # -2 = não existe, -1 = sem TTL, >=0 = segundos restantes
        except Exception as e:
            logger.warning("watchdog_ttl_error", conta_id=conta_id, key=key, error=str(e))
            ttl = -2

        precisa_renovar = (ttl == -2) or (ttl >= 0 and ttl <= REFRESH_THRESHOLD_SEC)

        if not precisa_renovar:
            continue

        # Carrega payload atual (se houver); mantém ordens acumuladas
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
            if ttl != -2:
                # pequeno "grace" para consumidores que ainda estiverem usando a antiga
                pipe.pexpire(key, GRACE_MS)
            pipe.execute()

            repo.atualizar_chave_token_conta_por_id(conta_id, new_key)
            logger.info(
                "watchdog_token_rotated",
                conta_id=conta_id,
                old_key=key,
                new_key=new_key,
                old_ttl=ttl,
            )
        except Exception as e:
            logger.error("watchdog_rotate_error", conta_id=conta_id, key=key, error=str(e))


async def _loop() -> None:
    logger.info("token_watchdog_start")
    # deixa o app subir por completo antes do primeiro tick
    await asyncio.sleep(0)
    while True:
        try:
            await asyncio.to_thread(_tick_once)
        except Exception as e:
            logger.error("token_watchdog_tick_error", error=str(e))
        await asyncio.sleep(INTERVAL_SEC)


def start_token_watchdog(app) -> None:
    """
    Inicia o watchdog em background. Chame isso apenas no serviço 'write'
    (ou onde você realmente precise do watchdog rodando).
    """
    app.state.token_watchdog_task = asyncio.create_task(_loop())


def stop_token_watchdog(app) -> None:
    """Cancela a task do watchdog no shutdown."""
    task = getattr(app.state, "token_watchdog_task", None)
    if task and not task.done():
        task.cancel()
