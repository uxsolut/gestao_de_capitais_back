# background/token_watchdog.py
import asyncio
import json
import secrets
import structlog
from typing import Optional, Dict, Any

from config import settings
from database import ProcessamentoRepository
from services.processamento_service import _redis_ordens, _generate_token

logger = structlog.get_logger()

# -------------------------
# Config (com defaults)
# -------------------------
TTL_SECONDS = int(getattr(settings, "TOKEN_TTL_SECONDS", 300))
REFRESH_THRESHOLD_SEC = int(getattr(settings, "TOKEN_WATCHDOG_REFRESH_THRESHOLD_SECONDS", 90))
GRACE_MS = int(getattr(settings, "TOKEN_WATCHDOG_GRACE_MS", 2000))
INTERVAL_SEC = float(getattr(settings, "TOKEN_WATCHDOG_INTERVAL_SECONDS", 10))
NAMESPACE = (getattr(settings, "OPAQUE_TOKEN_NAMESPACE", "tok") or "tok").strip()


def _key_from_db(db_val: Optional[str]) -> Optional[str]:
    """Garante que a chave tenha o namespace (ex.: 'tok:...')."""
    if not db_val:
        return None
    s = db_val.strip()
    return s if s.startswith(f"{NAMESPACE}:") else f"{NAMESPACE}:{s}"


def _raw_from_key(key: str) -> str:
    pref = f"{NAMESPACE}:"
    return key[len(pref):] if key.startswith(pref) else key


def _requisicao_id_from(numero_unico: Optional[str]) -> Optional[int]:
    """Extrai requisicao_id de 'REQ-<id>-<conta>' quando houver (legado)."""
    if numero_unico and numero_unico.startswith("REQ-"):
        try:
            _, sreq, _ = numero_unico.split("-", 2)
            return int(sreq)
        except Exception:
            return None
    return None


def _ensure_payload_v2(payload_str: Optional[str],
                       numero_unico: Optional[str],
                       conta: Optional[str]) -> Dict[str, Any]:
    """
    Retorna payload v2 no formato:
      {"conta": "...", "requisicao_id": int|None, "scope": "consulta_reqs", "ordens": [ ... ]}
    Converte legado quando necessário.
    """
    def _skeleton():
        return {
            "conta": (str(conta) if conta is not None else None),
            "requisicao_id": _requisicao_id_from(numero_unico),
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
        p.setdefault("conta", str(conta) if conta is not None else p.get("conta"))
        p.setdefault("scope", "consulta_reqs")
        p.setdefault("requisicao_id", p.get("requisicao_id", _requisicao_id_from(numero_unico)))
        return p

    # legado {"conta","requisicao_id","scope","ordem_id","dados":{...}}
    ordem = {}
    if isinstance(p, dict):
        if "ordem_id" in p:
            ordem["ordem_id"] = p.get("ordem_id")
        dados = p.get("dados") or {}
        for k in ("id_robo", "id_tipo_ordem", "tipo", "symbol"):
            if k in dados:
                ordem[k] = dados[k]
        novo = _skeleton()
        if ordem:
            novo["ordens"].append(ordem)
        return novo

    return _skeleton()


def _tick_once():
    """
    Uma passada do watchdog:
      1) Zera token de contas SEM ordens 'Inicializado'.
      2) Para contas COM 'Inicializado', garante chave no Redis e renova se TTL baixo/sumiu.
    """
    repo = ProcessamentoRepository()
    RO = _redis_ordens()

    # 1) Contas onde já é seguro limpar token (todas ordens consumidas)
    for row in repo.listar_contas_consumidas_com_token(limit=200):
        key_in_db = _key_from_db(row.get("chave_do_token"))
        conta_id = row.get("id")

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

    # 2) Contas que ainda têm ordens 'Inicializado' → precisam ter chave viva
    for row in repo.listar_ordens_inicializadas(limit=500):
        conta_id = row.get("id")  # ID da conta
        conta = row.get("conta_meta_trader")
        numero_unico = row.get("numero_unico")  # pode ser None (conta-based)
        db_val = row.get("chave_do_token")
        key = _key_from_db(db_val)

        # Sem chave no banco → criar
        if not key:
            payload_v2 = _ensure_payload_v2(None, numero_unico, conta)
            raw = _generate_token()  # usa secrets.token_urlsafe(32) internamente
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
            ttl = RO.ttl(key)  # -2 = não existe, -1 = sem TTL, >=0 = segundos
        except Exception as e:
            logger.warning("watchdog_ttl_error", conta_id=conta_id, key=key, error=str(e))
            ttl = -2

        precisa_renovar = (ttl == -2) or (ttl >= 0 and ttl <= REFRESH_THRESHOLD_SEC)

        if not precisa_renovar:
            continue

        try:
            payload_s = RO.get(key)
        except Exception as e:
            logger.warning("watchdog_get_payload_error", conta_id=conta_id, key=key, error=str(e))
            payload_s = None

        payload_v2 = _ensure_payload_v2(payload_s, numero_unico, conta)

        raw = secrets.token_urlsafe(32)
        new_key = f"{NAMESPACE}:{raw}"

        try:
            pipe = RO.pipeline()
            pipe.set(new_key, json.dumps(payload_v2, ensure_ascii=False), ex=TTL_SECONDS)
            if ttl != -2:
                # dá um pequeno "grace" na chave antiga para consumidores que ainda não atualizaram
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


async def _loop():
    logger.info("token_watchdog_start")
    # deixa o app subir por completo antes do primeiro tick
    await asyncio.sleep(0)
    while True:
        try:
            await asyncio.to_thread(_tick_once)
        except Exception as e:
            logger.error("token_watchdog_tick_error", error=str(e))
        await asyncio.sleep(INTERVAL_SEC)


def start_token_watchdog(app):
    # Inicie apenas quando quiser (ex.: apenas no serviço 'write')
    app.state.token_watchdog_task = asyncio.create_task(_loop())


def stop_token_watchdog(app):
    task = getattr(app.state, "token_watchdog_task", None)
    if task and not task.done():
        task.cancel()
