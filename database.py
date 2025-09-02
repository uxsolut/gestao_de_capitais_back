# -*- coding: utf-8 -*-
import os
from contextlib import contextmanager
from datetime import datetime
import json as py_json
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# ==========================
# Parte SQLAlchemy (ORM)
# ==========================
from sqlalchemy import create_engine, text  # text incluído como no seu original
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =======================================
# Parte PostgreSQL + Redis + Repository
# =======================================
import psycopg2  # noqa: F401 (mantido como no seu código)
import redis
import structlog
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from config import settings

logger = structlog.get_logger()


class DatabaseManager:
    def __init__(self):
        self.postgres_pool: Optional[ThreadedConnectionPool] = None
        self.redis_client: Optional[redis.Redis] = None
        self._initialize_connections()

    def _initialize_connections(self):
        """Inicializa as conexões com PostgreSQL e Redis"""
        try:
            # Pool de conexões PostgreSQL
            self.postgres_pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                host=settings.postgres_host,
                port=settings.postgres_port,
                database=settings.postgres_db,
                user=settings.postgres_user,
                password=settings.postgres_password,
                cursor_factory=RealDictCursor,
            )

            # Cliente Redis (um DB único; este repo usa para a fila por conta)
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )

            # Teste de conexões
            self._test_connections()
            logger.info("Conexões de banco inicializadas com sucesso")
        except Exception as e:
            logger.error("Erro ao inicializar conexões", error=str(e))
            raise

    def _test_connections(self):
        """Testa as conexões com os bancos"""
        with self.get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        self.redis_client.ping()

    @contextmanager
    def get_postgres_connection(self):
        """Context manager para conexões PostgreSQL"""
        conn = None
        try:
            conn = self.postgres_pool.getconn()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error("Erro na conexão PostgreSQL", error=str(e))
            raise
        finally:
            if conn:
                self.postgres_pool.putconn(conn)

    def get_redis_client(self) -> redis.Redis:
        """Retorna o cliente Redis"""
        if not self.redis_client:
            raise RuntimeError("Redis não inicializado")
        return self.redis_client

    def close_connections(self):
        """Fecha todas as conexões"""
        if self.postgres_pool:
            self.postgres_pool.closeall()
        if self.redis_client:
            self.redis_client.close()


# Instância global do gerenciador de banco
db_manager = DatabaseManager()


class ProcessamentoRepository:
    """Repository para processamento de requisições com isolamento por conta"""

    def __init__(self):
        self.db = db_manager
        self.redis = db_manager.get_redis_client()

    # ---------------- PostgreSQL ----------------
    def criar_requisicao(self, dados_requisicao: Dict[str, Any]) -> int:
        """
        Insere em requisicoes: id_robo, symbol, id_tipo_ordem (opcional), tipo (enum).
        """
        with self.db.get_postgres_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO requisicoes (id_robo, symbol, id_tipo_ordem, tipo)
                VALUES (%(id_robo)s, %(symbol)s, %(id_tipo_ordem)s, %(tipo)s::tipo_de_acao)
                RETURNING id
                """,
                {
                    "id_robo": dados_requisicao.get("id_robo"),
                    "symbol": dados_requisicao.get("symbol"),
                    "id_tipo_ordem": dados_requisicao.get("id_tipo_ordem"),
                    "tipo": (dados_requisicao.get("tipo") or "").upper(),
                },
            )
            requisicao_id = cursor.fetchone()["id"]
            conn.commit()
            logger.info("Requisição criada no PostgreSQL", requisicao_id=requisicao_id)
            return requisicao_id

    def buscar_contas_robos_ligados(self, id_robo: int) -> List[Dict[str, Any]]:
        with self.db.get_postgres_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    rdu.id      AS id_robo_user,
                    rdu.id_user AS id_user,
                    rdu.id_robo AS id_robo,
                    rdu.id_conta AS id_conta,
                    c.nome      AS nome_conta
                FROM robos_do_user rdu
                JOIN contas c ON rdu.id_conta = c.id
                WHERE rdu.id_robo = %s
                  AND rdu.ligado = TRUE
                """,
                (id_robo,),
            )
            return [dict(r) for r in cursor.fetchall()]

    def _criar_ordem_pg(self, conta: Dict[str, Any], requisicao_id: int, dados_requisicao: Dict[str, Any]) -> int:
        """
        Cria uma ordem ligada ao robô do usuário (id_robo_user). Não grava id_conta na tabela ordens
        porque essa coluna não existe; a associação com a conta é via robos_do_user.id_conta.
        """
        with self.db.get_postgres_connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO ordens (
                    id_robo_user, id_user, numero_unico, status, id_tipo_ordem, tipo
                )
                VALUES (%s, %s, %s, %s::ordem_status, %s, %s::tipo_de_acao)
                RETURNING id
                """,
                (
                    conta["id_robo_user"],
                    conta["id_user"],
                # numero_unico só como string (pode incluir o id_conta para facilitar leitura se quiser)
                    f"REQ-{requisicao_id}-conta-{conta['id_conta']}",
                    "Inicializado",
                    dados_requisicao.get("id_tipo_ordem"),
                    (dados_requisicao.get("tipo") or "").upper(),
                ),
            )
            ordem_id = cursor.fetchone()["id"]
            conn.commit()
            logger.debug(
                "Ordem criada no PostgreSQL",
                requisicao_id=requisicao_id,
                id_conta=conta["id_conta"],
                ordem_id=ordem_id,
            )
            return ordem_id

    def atualizar_chave_token_conta_por_id(self, id_conta: int, chave: Optional[str]) -> bool:
        """
        Atualiza/persiste a chave_do_token na tabela public.contas (por ID).
        Aceita 'tok:...' ou o token cru; sempre salva com namespace.
        Faz RETURNING para confirmar o que ficou salvo e loga.
        """
        try:
            # normaliza a chave (sempre com namespace)
            ns = (getattr(settings, "OPAQUE_TOKEN_NAMESPACE", "") or "tok").strip()
            if chave:
                chave_final = chave if ":" in chave else f"{ns}:{chave}"
            else:
                chave_final = None  # permite limpar se necessário

            with self.db.get_postgres_connection() as conn, conn.cursor() as c:
                c.execute(
                    """
                    UPDATE public.contas
                       SET chave_do_token = %s,
                           updated_at     = now()
                     WHERE id = %s
                 RETURNING chave_do_token
                    """,
                    (chave_final, id_conta),
                )
                row = c.fetchone()
                conn.commit()

            salvo = row["chave_do_token"] if row else None
            logger.info("chave_token_salva", id_conta=id_conta, chave_salva=salvo)
            return bool(salvo)
        except Exception as e:
            logger.error("atualizar_chave_token_conta_por_id_erro", id=id_conta, error=str(e))
            return False

    # ---------------- Redis (fila por conta – legado mantido) ----------------
    def organizar_redis_por_conta(self, requisicao_id: int, dados_requisicao: Dict[str, Any], contas: List[Dict[str, Any]]) -> Dict[str, Any]:
        resultado = {"contas_processadas": 0, "contas_com_erro": 0, "detalhes": []}

        payload = {
            "requisicao_id": requisicao_id,
            "tipo": (dados_requisicao.get("tipo") or "").upper(),
            "symbol": dados_requisicao.get("symbol"),
            "id_robo": dados_requisicao.get("id_robo"),
            "comentario_ordem": dados_requisicao.get("comentario_ordem"),
            "quantidade": dados_requisicao.get("quantidade"),
            "preco": dados_requisicao.get("preco"),
            "dados_adicionais": dados_requisicao.get("dados_adicionais") or {},
            "criado_em": datetime.utcnow().isoformat(),
        }
        payload_str = py_json.dumps(payload, ensure_ascii=False)
        contas_vistas: set[int] = set()

        for conta in contas:
            try:
                id_conta = int(conta["id_conta"])
                id_robo_user = conta["id_robo_user"]

                key_reqs = f"conta:{id_conta}:reqs"
                key_set  = f"conta:{id_conta}:robos"
                key_meta = f"conta:{id_conta}:meta"

                pipe = self.redis.pipeline()
                pipe.sadd(key_set, str(id_robo_user))
                pipe.hset(
                    key_meta,
                    mapping={
                        "ultima_requisicao_id": str(requisicao_id),
                        "ultima_atualizacao": datetime.utcnow().isoformat(),
                    },
                )
                if id_conta not in contas_vistas:
                    pipe.rpush(key_reqs, payload_str)
                    contas_vistas.add(id_conta)
                pipe.execute()

                ordem_id = self._criar_ordem_pg(conta, requisicao_id, dados_requisicao)
                resultado["contas_processadas"] += 1
                resultado["detalhes"].append(
                    {
                        "id_conta": id_conta,
                        "conta": str(id_conta),
                        "status": "sucesso",
                        "id_ordem": ordem_id,
                        "id_tipo_ordem": dados_requisicao.get("id_tipo_ordem"),
                        "tipo": (dados_requisicao.get("tipo") or "").upper(),
                    }
                )
            except Exception as e:
                logger.error("Erro ao organizar Redis/PG para conta", conta=conta, error=str(e))
                resultado["contas_com_erro"] += 1
                resultado["detalhes"].append(
                    {"conta": str(conta.get("id_conta", "unknown")), "status": "erro", "erro": str(e)}
                )

        logger.info("Processamento (Redis + ordens) concluído", requisicao_id=requisicao_id, **resultado)
        return resultado

    # ---------------- Logs ----------------
    def registrar_log(
        self,
        tipo: str,
        conteudo: str,
        id_usuario: int,
        id_aplicacao: int = 1,
        id_robo_user: Optional[int] = None,
        id_robo: Optional[int] = None,
        id_conta: Optional[int] = None,
    ):
        try:
            with self.db.get_postgres_connection() as conn, conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO logs (
                        tipo, conteudo, id_usuario, id_aplicacao, id_robo_user, id_robo, id_conta
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        tipo,
                        conteudo,
                        id_usuario,
                        id_aplicacao,
                        id_robo_user,
                        id_robo,
                        id_conta,
                    ),
                )
                conn.commit()
            logger.debug("Log registrado", tipo=tipo, usuario=id_usuario)
        except Exception as e:
            logger.error("Erro ao registrar log", error=str(e))
    
    def limpar_chave_token_por_id(self, conta_id: int):
        """Zera a coluna chave_do_token da TABELA CONTAS."""
        try:
            with self.db.get_postgres_connection() as conn, conn.cursor() as c:
                c.execute(
                    """
                    UPDATE public.contas
                       SET chave_do_token = NULL,
                           updated_at = now()
                     WHERE id = %s
                    """,
                    (conta_id,),
                )
                conn.commit()
        except Exception as e:
            logger.error(
                "limpar_chave_token_conta_por_id_erro", id=conta_id, error=str(e)
            )

    def atualizar_chave_token_por_id(self, conta_id: int, novo_token: Optional[str]) -> bool:
        """Compat: atualiza chave_do_token em CONTAS (nome mantido pro watchdog)."""
        try:
            with self.db.get_postgres_connection() as conn, conn.cursor() as c:
                c.execute(
                    """
                    UPDATE public.contas
                       SET chave_do_token = %s,
                           updated_at = now()
                     WHERE id = %s
                    """,
                    (novo_token, conta_id),
                )
                conn.commit()
                return c.rowcount > 0
        except Exception as e:
            logger.error(
                "atualizar_chave_token_por_id_erro", id=conta_id, error=str(e)
            )
            return False
    
    def excluir_ordem_por_id(self, ordem_id: int) -> bool:
        with self.db.get_postgres_connection() as conn, conn.cursor() as c:
            c.execute("DELETE FROM public.ordens WHERE id = %s", (ordem_id,))
            conn.commit()
            return c.rowcount > 0
        
    def buscar_chave_token_ativa_por_id(self, id_conta: int) -> Optional[str]:
        """
        Retorna a chave_do_token salva em public.contas para a conta (por ID).
        """
        try:
            with self.db.get_postgres_connection() as conn, conn.cursor() as c:
                c.execute(
                    "SELECT chave_do_token FROM public.contas WHERE id = %s LIMIT 1",
                    (id_conta,),
                )
                row = c.fetchone()
                return row["chave_do_token"] if row else None
        except Exception as e:
            logger.error("buscar_chave_token_ativa_por_id_erro", id_conta=id_conta, error=str(e))
            return None
        
    def listar_contas_com_inicializado(self, limit: int = 2000):
        """
        CONTAS que possuem AO MENOS uma ORDEM em 'Inicializado'.
        Join: ordens.id_robo_user -> robos_do_user.id -> robos_do_user.id_conta -> contas.id
        Retorna: [{"id": <conta_id>, "chave_do_token": <str|None>}]
        """
        try:
            with self.db.get_postgres_connection() as conn, conn.cursor() as c:
                c.execute(
                    """
                    SELECT c.id AS id, c.chave_do_token
                      FROM public.contas c
                     WHERE EXISTS (
                            SELECT 1
                              FROM public.ordens o
                              JOIN public.robos_do_user rdu
                                ON rdu.id = o.id_robo_user
                             WHERE rdu.id_conta = c.id
                               AND o.status = 'Inicializado'::ordem_status
                           )
                  ORDER BY c.id DESC
                     LIMIT %s
                    """,
                    (limit,),
                )
                return [dict(r) for r in c.fetchall()]
        except Exception as e:
            logger.error("listar_contas_com_inicializado_erro", error=str(e))
            return []
    def listar_contas_sem_inicializado_com_token(self, limit: int = 1000):
        """
        CONTAS que têm chave_do_token, mas NÃO possuem NENHUMA ordem em 'Inicializado'.
        Aqui podemos apagar a chave no Redis e zerar no banco.
        Retorna: [{"id": <conta_id>, "chave_do_token": <str>}]
        """
        try:
            with self.db.get_postgres_connection() as conn, conn.cursor() as c:
                c.execute(
                    """
                    SELECT c.id AS id, c.chave_do_token
                      FROM public.contas c
                     WHERE c.chave_do_token IS NOT NULL
                       AND NOT EXISTS (
                            SELECT 1
                              FROM public.ordens o
                              JOIN public.robos_do_user rdu
                                ON rdu.id = o.id_robo_user
                             WHERE rdu.id_conta = c.id
                               AND o.status = 'Inicializado'::ordem_status
                           )
                  ORDER BY c.id DESC
                     LIMIT %s
                    """,
                    (limit,),
                )
                return [dict(r) for r in c.fetchall()]
        except Exception as e:
            logger.error("listar_contas_sem_inicializado_com_token_erro", error=str(e))
            return []
