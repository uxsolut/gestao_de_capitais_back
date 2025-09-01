# services/processamento_service.py
import time
import json
import secrets
from typing import Dict, Any, Union, Optional, List

import redis
import structlog

from database import ProcessamentoRepository
from schemas.requisicoes import (
    ProcessamentoResponse, StatusResponse, ErrorResponse, ContaProcessada
)
from config import settings

logger = structlog.get_logger()


# ------------------------ Redis helpers ------------------------
def _redis_ordens() -> redis.Redis:
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
        db=int(getattr(settings, "REDIS_DB_ORDENS", 1)),
        decode_responses=True,
    )


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def _ns() -> str:
    ns = (getattr(settings, "OPAQUE_TOKEN_NAMESPACE", "") or "").strip() or "tok"
    return ns


def _make_key(token: str) -> str:
    ns = _ns()
    return token if token.startswith(f"{ns}:") else f"{ns}:{token}"


def _ensure_payload_v2(payload_str: Optional[str]) -> Dict[str, Any]:
    """
    Garante um payload no formato v2:
      {"conta": "<id_conta>", "requisicao_id": int, "scope": "consulta_reqs", "ordens": [ {...} ]}
    """
    if not payload_str:
        return {}
    try:
        p = json.loads(payload_str)
    except Exception:
        return {}
    # já é v2
    if isinstance(p, dict) and "ordens" in p:
        return p
    # fallback tosco: empacota no formato novo
    return {"ordens": []}


# def _mask(tok: str) -> str:
#     return tok[:4] + "..." + tok[-4:] if tok and len(tok) >= 8 else (tok or "")


class ProcessamentoService:
    """
    Serviço de negócio para processamento de requisições.

    Política (somente por CONTA):
      - Seleciona contas que tenham o robô ligado (robos_do_user.ligado = true) e id_conta definido.
      - Um token opaco por CONTA (chave Redis por conta).
      - Se já houver payload para a conta, SUBSTITUI a ordem do mesmo id_robo; senão, insere.
      - Persiste a chave (string completa, ex.: "tok:abc...") em contas.chave_do_token.
    """

    def __init__(self):
        self.repository = ProcessamentoRepository()
        self._token_ttl = int(getattr(settings, "TOKEN_TTL_SECONDS", 300))  # default 5 min

    async def processar_requisicao(
        self,
        dados_requisicao: Dict[str, Any],
        user_data: Dict[str, Any],
    ) -> Union[ProcessamentoResponse, ErrorResponse]:
        inicio = time.time()

        try:
            system_user_id = user_data.get("system_user_id") or getattr(settings, "SYSTEM_USER_ID", 1)
            id_robo = int(dados_requisicao["id_robo"])

            logger.info("proc_req_in", id_robo=id_robo, actor=user_data.get("role", "system"))

            # 1) cria a requisição
            requisicao_id = self.repository.criar_requisicao(dados_requisicao)

            self.repository.registrar_log(
                tipo="notificacao",
                conteudo=f"Requisição {requisicao_id} criada para robô {id_robo}",
                id_usuario=system_user_id,
                id_aplicacao=1,
                id_robo=id_robo,
            )

            # 2) busca SOMENTE contas com robô ligado e id_conta definido
            # formato esperado de cada item: {"id_conta": int, "nome": str, "id_user": int, "id_robo_user": int}
            contas: List[Dict[str, Any]] = self.repository.buscar_contas_robos_ligados(id_robo)
            contas = [c for c in contas if c.get("id_conta") is not None]
            if not contas:
                tempo = time.time() - inicio
                logger.warning("no_accounts_for_robot", id_robo=id_robo)
                self.repository.registrar_log(
                    tipo="problema",
                    conteudo=f"Nenhuma conta ligada encontrada para robô {id_robo}",
                    id_usuario=system_user_id,
                    id_aplicacao=1,
                    id_robo=id_robo,
                )
                return ErrorResponse(
                    message=f"Nenhuma conta com robô {id_robo} ligado encontrada",
                    error_code="NO_ACCOUNTS_FOUND",
                    tempo_processamento=tempo,
                )

            # 3) delega criação de ordens por conta (repo retorna ordem_id por conta)
            resultado_repo = self.repository.organizar_redis_por_conta(
                requisicao_id, dados_requisicao, contas
            )
            # esperado: {"detalhes":[{"id_conta":int,"status":"sucesso","ordem_id":int}, ...], ...}

            # mapa rápido por id_conta -> detalhe
            detalhes_repo_por_id: Dict[str, Dict[str, Any]] = {}
            for d in resultado_repo.get("detalhes", []):
                cid = d.get("id_conta")
                if cid is not None:
                    detalhes_repo_por_id[str(int(cid))] = d

            # 4) monta/atualiza Redis por CONTA e persiste chave em contas
            RO = _redis_ordens()
            tokens_por_conta: Dict[str, str] = {}
            detalhes_resp: List[Dict[str, Any]] = []

            for c in contas:
                conta_id = int(c["id_conta"])
                conta_nome = c.get("nome") or str(conta_id)
                # detalhe do repo para esta conta (pega ordem_id, status etc.)
                det = detalhes_repo_por_id.get(str(conta_id), {}) or {}
                status_det = str(det.get("status", "sucesso")).lower()
                ordem_id = det.get("ordem_id")

                # estrutura base de retorno por conta
                det_out = {
                    "conta": str(conta_id),
                    "status": "sucesso" if status_det in ("sucesso", "success", "ok") else status_det,
                    "token_gerado": False,
                    "token": None,
                    "ordem_id": ordem_id,
                }

                if ordem_id is None or status_det not in ("sucesso", "success", "ok"):
                    detalhes_resp.append(det_out)
                    continue

                # ordem a colocar/substituir no payload
                nova_ordem = {
                    "ordem_id": ordem_id,
                    "id_robo": id_robo,
                    "id_tipo_ordem": dados_requisicao.get("id_tipo_ordem"),
                    "tipo": str(dados_requisicao.get("tipo")).upper(),
                    "symbol": dados_requisicao.get("symbol"),
                }

                # 4.1 chave ativa desta CONTA (se houver)
                chave_existente: Optional[str] = self.repository.buscar_chave_token_ativa_por_id(conta_id)

                if chave_existente:
                    # carrega payload v2 e substitui a ordem do MESMO id_robo
                    payload_v2 = _ensure_payload_v2(RO.get(chave_existente)) or {
                        "conta": str(conta_id),
                        "requisicao_id": requisicao_id,
                        "scope": "consulta_reqs",
                        "ordens": [],
                    }
                    payload_v2["conta"] = str(conta_id)
                    payload_v2["requisicao_id"] = requisicao_id

                    ordens_list = list(payload_v2.get("ordens") or [])
                    replaced = False
                    for i, o in enumerate(list(ordens_list)):
                        try:
                            if int(o.get("id_robo")) == id_robo:
                                old_id = o.get("ordem_id")
                                ordens_list[i] = nova_ordem
                                replaced = True
                                # exclui a ordem antiga no Postgres (se era de outro envio)
                                if old_id and old_id != ordem_id:
                                    try:
                                        self.repository.excluir_ordem_por_id(int(old_id))
                                    except Exception as e:
                                        logger.warning("fail_delete_old_order", conta_id=conta_id, error=str(e))
                                break
                        except Exception:
                            continue
                    if not replaced:
                        ordens_list.append(nova_ordem)

                    payload_v2["ordens"] = ordens_list
                    RO.set(chave_existente, json.dumps(payload_v2), ex=self._token_ttl)

                    # garante persistência da chave (id_conta)
                    self.repository.atualizar_chave_token_conta_por_id(conta_id, chave_existente)

                    det_out["token_gerado"] = True
                    det_out["token"] = chave_existente.split(":", 1)[1] if ":" in chave_existente else chave_existente
                    tokens_por_conta[str(conta_id)] = det_out["token"]

                else:
                    # 4.2 nova chave por CONTA
                    token_cru = _generate_token()
                    chave_token = _make_key(token_cru)

                    payload_v2 = {
                        "conta": str(conta_id),
                        "requisicao_id": requisicao_id,
                        "scope": "consulta_reqs",
                        "ordens": [nova_ordem],
                    }
                    RO.set(chave_token, json.dumps(payload_v2), ex=self._token_ttl)

                    # persiste a chave (id_conta)
                    self.repository.atualizar_chave_token_conta_por_id(conta_id, chave_token)

                    det_out["token_gerado"] = True
                    det_out["token"] = token_cru  # se quiser mascarar, use _mask(token_cru)
                    tokens_por_conta[str(conta_id)] = token_cru

                # log útil por conta
                self.repository.registrar_log(
                    tipo="notificacao",
                    conteudo=f"Redis organizado para requisicao {requisicao_id} (conta {conta_nome})",
                    id_usuario=c.get("id_user"),
                    id_aplicacao=1,
                    id_robo_user=c.get("id_robo_user"),
                    id_robo=id_robo,
                    id_conta=conta_id,
                )

                detalhes_resp.append(det_out)

            tempo = time.time() - inicio

            return ProcessamentoResponse(
                id=requisicao_id,
                status="success",
                message="Requisição processada e organizada no Redis por conta",
                contas_processadas=len(contas),
                contas_com_erro=0,
                detalhes=[ContaProcessada(**d) for d in detalhes_resp],
                tempo_processamento=tempo,
                tokens_por_conta=tokens_por_conta or None,
            )

        except Exception as e:
            tempo = time.time() - inicio
            logger.error("proc_req_error", error=str(e), tempo=tempo)
            try:
                self.repository.registrar_log(
                    tipo="problema",
                    conteudo=f"Erro no processamento: {str(e)}",
                    id_usuario=user_data.get("system_user_id") or getattr(settings, "SYSTEM_USER_ID", 1),
                    id_aplicacao=1,
                    id_robo=dados_requisicao.get("id_robo"),
                )
            except Exception:
                pass

            return ErrorResponse(
                message=f"Erro interno no processamento: {str(e)}",
                error_code="INTERNAL_ERROR",
                tempo_processamento=tempo,
            )

    async def verificar_status_requisicao(
        self,
        requisicao_id: int,
        user_data: Dict[str, Any],
    ) -> Union[StatusResponse, ErrorResponse]:
        inicio = time.time()
        try:
            logger.info("check_status_requisicao", requisicao_id=requisicao_id)
            tempo = time.time() - inicio
            return StatusResponse(
                id=requisicao_id,
                status="processed",
                contas_encontradas=0,
                redis_organizado=True,
                tempo_processamento=tempo,
            )
        except Exception as e:
            tempo = time.time() - inicio
            logger.error("status_error", requisicao_id=requisicao_id, error=str(e))
            return ErrorResponse(
                message=f"Erro ao verificar status: {str(e)}",
                error_code="STATUS_CHECK_ERROR",
                tempo_processamento=tempo,
            )
