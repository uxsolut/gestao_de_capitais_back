# background/token_watchdog.py
import asyncio
import json
import structlog
from typing import Optional, Dict, Any

from config import settings
from database import ProcessamentoRepository
from services.processamento_service import _redis_ordens, _generate_token

logger = structlog.get_logger()

# Limiares/intervalos
ROTATE_THRESHOLD_MS = int(getattr(settings, "TOKEN_ROTATE_THRESHOLD_MS", 3000))
GRACE_MS            = int(getattr(settings, "TOKEN_GRACE_MS", 2000))
INTERVAL_MS         = int(getattr(settings, "TOKEN_WATCHDOG_INTERVAL_MS", 1000))


def _ensure_payload_v2(payload_str: Optional[str], numero_unico: Optional[str], conta: Optional[str]) -> Dict[str, Any]:
    """
    Garante o formato v2 do payload:
      {"conta": "...", "requisicao_id": int|None, "scope": "consulta_reqs", "ordens": [ {...} ]}
    Se o payload existente estiver no formato legado, converte para v2.
    Se não houver payload, constrói um “esqueleto” v2 vazio.
    """
    # esqueleto (usado como fallback)
    def _skeleton():
        return {
            "conta": str(conta) if conta is not None else None,
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
        # já está no formato novo
        # garante chaves mínimas
        p.setdefault("conta", str(conta) if conta is not None else p.get("conta"))
        p.setdefault("scope", "consulta_reqs")
        p.setdefault("requisicao_id", p.get("requisicao_id", _requisicao_id_from(numero_unico)))
        return p

    # legado esperado: {"conta","requisicao_id","scope","ordem_id","dados":{...}}
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


def _requisicao_id_from(numero_unico: Optional[str]) -> Optional[int]:
    """Extrai requisicao_id de 'REQ-<id>-<conta>' quando houver."""
    if numero_unico and numero_unico.startswith("REQ-"):
        try:
            _, sreq, _ = numero_unico.split("-", 2)
            return int(sreq)
        except Exception:
            return None
    return None


def _tick_once():
    """Executa UMA passada de limpeza/rotação (síncrono; roda em thread)."""
    repo = ProcessamentoRepository()
    RO = _redis_ordens()
    ttl_seconds = int(getattr(settings, "TOKEN_TTL_SECONDS", 300))

    # 1) Limpar tokens de CONTAS “consumidas” (regra simplificada conforme repo)
    for row in repo.listar_ordens_consumidas_com_token(limit=200):
        key = (row.get("chave_do_token") or "").strip()
        try:
            if key:
                RO.delete(key)  # key já no formato "tok:..."
        except Exception as e:
            logger.warning("watchdog_delete_fail", key=key, error=str(e))
        # Agora opera em CONTAS
        try:
            repo.limpar_chave_token_por_id(row["id"])
        except Exception as e:
            logger.warning("watchdog_db_clear_fail", conta_id=row.get("id"), error=str(e))

    # 2) Emitir/rotacionar para CONTAS com token ativo
    for row in repo.listar_ordens_inicializadas(limit=500):
        key_in_db    = (row.get("chave_do_token") or "").strip()
        numero_unico = row.get("numero_unico")        # pode ser None (agora é conta-based)
        conta        = row.get("conta_meta_trader")   # string da conta
        conta_id     = row.get("id")                  # id da CONTA

        if not key_in_db:
            # Sem chave em DB: cria nova chave com payload v2 “vazio”
            payload_v2 = _ensure_payload_v2(None, numero_unico, conta)
            new_tok = _generate_token()
            new_key = f"tok:{new_tok}"
            try:
                RO.set(new_key, json.dumps(payload_v2), ex=ttl_seconds)
                repo.atualizar_chave_token_por_id(conta_id, new_key)  # agora é conta_id
                logger.info("watchdog_emitido", conta_id=conta_id, key=new_key)
            except Exception as e:
                logger.error("watchdog_emitir_erro", conta_id=conta_id, error=str(e))
            continue

        key    = key_in_db
        try:
            ttl_ms = RO.pttl(key)  # -2 (não existe), -1 (sem TTL), >=0 (ms restantes)
        except Exception as e:
            logger.warning("watchdog_pttl_erro", conta_id=conta_id, key=key, error=str(e))
            ttl_ms = -2

        if ttl_ms == -2 or ttl_ms <= ROTATE_THRESHOLD_MS:
            try:
                payload_s = RO.get(key)
            except Exception as e:
                logger.warning("watchdog_get_payload_erro", conta_id=conta_id, key=key, error=str(e))
                payload_s = None

            payload_v2 = _ensure_payload_v2(payload_s, numero_unico, conta)

            new_tok = _generate_token()
            new_key = f"tok:{new_tok}"

            try:
                pipe = RO.pipeline()
                pipe.set(new_key, json.dumps(payload_v2), ex=ttl_seconds)
                if ttl_ms != -2:
                    # dá um período de graça para consumidores que porventura ainda usem a chave antiga
                    pipe.pexpire(key, GRACE_MS)
                pipe.execute()

                # Atualiza a CONTA com a nova chave
                repo.atualizar_chave_token_por_id(conta_id, new_key)

                logger.info(
                    "watchdog_rotacionado",
                    conta_id=conta_id,
                    old_key=key,
                    new_key=new_key,
                    old_ttl_ms=ttl_ms
                )
            except Exception as e:
                logger.error("watchdog_rotacao_erro", conta_id=conta_id, key=key, error=str(e))


async def _loop():
    logger.info("token_watchdog_start")
    # dá chance de o startup finalizar antes do primeiro tick
    await asyncio.sleep(0)
    while True:
        try:
            # roda a passada síncrona fora do event loop
            await asyncio.to_thread(_tick_once)
        except Exception as e:
            logger.error("token_watchdog_erro", error=str(e))
        await asyncio.sleep(INTERVAL_MS / 1000.0)


def start_token_watchdog(app):
    loop = asyncio.get_running_loop()
    app.state.token_watchdog_task = loop.create_task(_loop())


def stop_token_watchdog(app):
    task = getattr(app.state, "token_watchdog_task", None)
    if task and not task.done():
        task.cancel()
