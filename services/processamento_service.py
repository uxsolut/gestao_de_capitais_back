# services/processamento_service.py
import time
import json
import secrets
from typing import Dict, Any, Union, Optional

import redis
import structlog

from database import ProcessamentoRepository
from schemas.requisicoes import (
    ProcessamentoResponse, StatusResponse, ErrorResponse, ContaProcessada
)
from config import settings

logger = structlog.get_logger()


# ------------------------
# Redis helpers
# ------------------------
def _redis_global():
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
        db=int(getattr(settings, "REDIS_DB_GLOBAL", 0)),
        decode_responses=True,
    )


def _redis_ordens():
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


# --- compat: converte payload antigo -> v2 (com lista de ordens) -----------------
def _ensure_payload_v2(payload_str: Optional[str]) -> Dict[str, Any]:
    """
    Se 'payload_str' for None/legado, retorna um objeto no formato:
    {"conta": "...", "requisicao_id": int, "scope": "consulta_reqs", "ordens": [ {...} ]}
    """
    if not payload_str:
        return {}
    try:
        p = json.loads(payload_str)
    except Exception:
        return {}

    if isinstance(p, dict) and "ordens" in p:
        return p  # já no formato novo

    # legado esperado: {"conta", "requisicao_id", "scope", "ordem_id", "dados": {...}}
    ordem = {}
    if isinstance(p, dict):
        if "ordem_id" in p:
            ordem["ordem_id"] = p.get("ordem_id")
        dados = p.get("dados") or {}
        for k in ("id_robo", "id_tipo_ordem", "tipo", "symbol"):
            if k in dados:
                ordem[k] = dados[k]
        novo = {
            "conta": p.get("conta"),
            "requisicao_id": p.get("requisicao_id"),
            "scope": p.get("scope", "consulta_reqs"),
            "ordens": [ordem] if ordem else [],
        }
        return novo

    return {}


class ProcessamentoService:
    """
    Serviço de negócio para processamento de requisições.

    NOVO FLUXO:
      - Um token por CONTA (chave Redis compartilhada).
      - Grava payload em Redis no formato v2: {"ordens": [...] } acumulando múltiplas ordens.
      - Se já houver ordem do MESMO id_robo na conta, SUBSTITUI a antiga (e deleta/fecha no PG).
      - Salva/atualiza a MESMA chave em contas.chave_do_token.
      - Consumidor faz GETDEL(chave) e processa todas as ordens.
    """

    def __init__(self):
        self.repository = ProcessamentoRepository()
        self._token_ttl = int(getattr(settings, "TOKEN_TTL_SECONDS", 300))  # 5 min

    async def processar_requisicao(
        self,
        dados_requisicao: Dict[str, Any],
        user_data: Dict[str, Any],
    ) -> Union[ProcessamentoResponse, ErrorResponse]:
        start_time = time.time()

        try:
            user_id = user_data.get("system_user_id") or getattr(settings, "SYSTEM_USER_ID", 1)
            id_robo = dados_requisicao["id_robo"]

            logger.info(
                "Iniciando processamento de requisicao",
                id_robo=id_robo,
                actor=user_data.get("role", "system"),
            )

            # 1) Cria requisição
            requisicao_id = self.repository.criar_requisicao(dados_requisicao)

            self.repository.registrar_log(
                tipo="notificacao",
                conteudo=f"Requisição {requisicao_id} criada para robô {id_robo}",
                id_usuario=user_id,
                id_aplicacao=1,
                id_robo=id_robo,
            )

            # 2) Contas com robôs ligados
            contas = self.repository.buscar_contas_robos_ligados(id_robo)
            if not contas:
                tempo_processamento = time.time() - start_time
                logger.warning("Nenhuma conta com robo ligado encontrada", id_robo=id_robo)
                self.repository.registrar_log(
                    tipo="problema",
                    conteudo=f"Nenhuma conta ligado encontrada para robô {id_robo}",
                    id_usuario=user_id,
                    id_aplicacao=1,
                    id_robo=id_robo,
                )
                return ErrorResponse(
                    message=f"Nenhuma conta com robô {id_robo} ligado encontrada",
                    error_code="NO_ACCOUNTS_FOUND",
                    tempo_processamento=tempo_processamento,
                )

            # 3) Organiza por conta (repo cria ordens e retorna ordem_id por conta)
            resultado_redis = self.repository.organizar_redis_por_conta(
                requisicao_id, dados_requisicao, contas
            )
            # esperado: detalhes = [ { "conta": <string>, "status": "sucesso", "ordem_id": int, ... } ]

            # 4) Logs por conta
            for conta in contas:
                self.repository.registrar_log(
                    tipo="notificacao",
                    conteudo=f"Redis organizado para requisicao {requisicao_id}",
                    id_usuario=conta.get("id_user"),
                    id_aplicacao=1,
                    id_robo_user=conta.get("id_robo_user"),
                    id_robo=id_robo,
                    id_conta=conta.get("id_conta"),
                )

            # índice auxiliar: conta_meta_trader -> linha
            conta_index: Dict[str, Any] = {}
            for c in contas:
                key = str(c.get("conta_meta_trader") or c.get("conta") or "").strip()
                if key:
                    conta_index[key] = c

            # 5) Token/chave e payload v2 (compartilhado por conta)
            RO = _redis_ordens()
            tokens_por_conta: Dict[str, str] = {}
            detalhes_enriquecidos = []

            # helper: persistir a chave na conta (por id e fallback por conta_meta)
            def _persist_chave(conta_meta: str, chave: str) -> None:
                conta_meta = (conta_meta or "").strip()
                ok = False
                row = conta_index.get(conta_meta)

                if row and row.get("id_conta"):
                    ok = self.repository.atualizar_chave_token_conta_por_id(row["id_conta"], chave)

                if not ok:
                    ok = self.repository.atualizar_chave_token_conta_por_meta(conta_meta, chave)

                if not ok:
                    logger.error(
                        "falha_ao_salvar_chave_na_conta",
                        conta=conta_meta,
                        id_conta=(row or {}).get("id_conta"),
                        chave=chave,
                    )

            for det in resultado_redis.get("detalhes", []):
                detalhe = dict(det)
                conta_id_str = str(detalhe.get("conta", "")).strip()
                status_conta = str(detalhe.get("status", "")).lower()
                ordem_id = detalhe.get("ordem_id")

                detalhe.setdefault("token_gerado", False)
                detalhe.setdefault("token", None)

                if status_conta in ("sucesso", "success", "ok") and ordem_id is not None:
                    try:
                        # ordem a acrescentar
                        nova_ordem = {
                            "ordem_id": ordem_id,
                            "id_robo": dados_requisicao.get("id_robo"),
                            "id_tipo_ordem": detalhe.get("id_tipo_ordem", dados_requisicao.get("id_tipo_ordem")),
                            "tipo": str(dados_requisicao.get("tipo")).upper(),
                            "symbol": dados_requisicao.get("symbol"),
                        }

                        # chave atual por conta (se existir)
                        chave_existente = self.repository.buscar_chave_token_ativa_por_conta(conta_id_str)

                        if chave_existente:
                            # ----- REPLACE-BY-ROBO -----
                            payload_v2 = _ensure_payload_v2(RO.get(chave_existente)) or {
                                "conta": conta_id_str,
                                "requisicao_id": requisicao_id,
                                "scope": "consulta_reqs",
                                "ordens": [],
                            }
                            payload_v2["requisicao_id"] = requisicao_id

                            ordens_list = payload_v2.get("ordens")
                            if not isinstance(ordens_list, list):
                                ordens_list = []

                            replaced = False
                            for i, o in enumerate(list(ordens_list)):
                                try:
                                    if str(o.get("id_robo")) == str(dados_requisicao.get("id_robo")):
                                        old_id = o.get("ordem_id")
                                        # substitui a ordem antiga pela nova
                                        ordens_list[i] = nova_ordem
                                        replaced = True

                                        # >>> EXCLUI a ordem antiga no Postgres (definitivo)
                                        try:
                                            if old_id and old_id != ordem_id:
                                                removed = self.repository.excluir_ordem_por_id(int(old_id))
                                                logger.info(
                                                    "ordem_substituida_e_excluida",
                                                    conta=conta_id_str,
                                                    ordem_antiga=old_id,
                                                    ordem_nova=ordem_id,
                                                    removed=bool(removed),
                                                )
                                        except Exception as e:
                                            logger.warning(
                                                "falha_excluir_ordem_antiga",
                                                conta=conta_id_str,
                                                ordem_antiga=old_id,
                                                error=str(e),
                                            )
                                        break
                                except Exception:
                                    continue

                            if not replaced:
                                # robô diferente → acumula
                                ordens_list.append(nova_ordem)

                            payload_v2["ordens"] = ordens_list

                            RO.set(chave_existente, json.dumps(payload_v2), ex=self._token_ttl)
                            _persist_chave(conta_id_str, chave_existente)

                            detalhe["token_gerado"] = True
                            detalhe["token"] = chave_existente.split(":", 1)[1] if ":" in chave_existente else None
                            if detalhe["token"]:
                                tokens_por_conta[conta_id_str] = detalhe["token"]

                        else:
                            # cria nova chave e grava primeira ordem
                            token_cru = _generate_token()
                            chave_token = _make_key(token_cru)

                            payload_v2 = {
                                "conta": conta_id_str,
                                "requisicao_id": requisicao_id,
                                "scope": "consulta_reqs",
                                "ordens": [nova_ordem],
                            }
                            RO.set(chave_token, json.dumps(payload_v2), ex=self._token_ttl)
                            _persist_chave(conta_id_str, chave_token)

                            detalhe["token_gerado"] = True
                            detalhe["token"] = token_cru
                            tokens_por_conta[conta_id_str] = token_cru

                    except Exception as e:
                        logger.error(
                            "Falha ao gerar/salvar token opaco para conta",
                            conta=conta_id_str,
                            requisicao_id=requisicao_id,
                            ordem_id=ordem_id,
                            error=str(e),
                        )

                detalhes_enriquecidos.append(detalhe)

            tempo_processamento = time.time() - start_time

            logger.info(
                "Processamento concluido com sucesso",
                requisicao_id=requisicao_id,
                contas_processadas=resultado_redis.get("contas_processadas"),
                tempo=tempo_processamento,
            )

            detalhes_processados = [ContaProcessada(**d) for d in detalhes_enriquecidos]

            return ProcessamentoResponse(
                id=requisicao_id,
                status="success",
                message="Requisição processada e organizada no Redis por conta",
                contas_processadas=resultado_redis.get("contas_processadas", 0),
                contas_com_erro=resultado_redis.get("contas_com_erro", 0),
                detalhes=detalhes_processados,
                tempo_processamento=tempo_processamento,
                tokens_por_conta=tokens_por_conta or None,
            )

        except Exception as e:
            tempo_processamento = time.time() - start_time
            logger.error("Erro no processamento de requisicao", error=str(e), tempo=tempo_processamento)
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
                tempo_processamento=tempo_processamento,
            )

    async def verificar_status_requisicao(
        self,
        requisicao_id: int,
        user_data: Dict[str, Any],
    ) -> Union[StatusResponse, ErrorResponse]:
        start_time = time.time()
        try:
            logger.info("Verificando status da requisicao", requisicao_id=requisicao_id)
            tempo_processamento = time.time() - start_time
            return StatusResponse(
                id=requisicao_id,
                status="processed",
                contas_encontradas=0,
                redis_organizado=True,
                tempo_processamento=tempo_processamento,
            )
        except Exception as e:
            tempo_processamento = time.time() - start_time
            logger.error("Erro na verificacao de status", requisicao_id=requisicao_id, error=str(e))
            return ErrorResponse(
                message=f"Erro ao verificar status: {str(e)}",
                error_code="STATUS_CHECK_ERROR",
                tempo_processamento=tempo_processamento,
            )
