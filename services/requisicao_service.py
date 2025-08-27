"""
Serviço para gerenciar requisições e integração com cache Redis
"""
import json
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_

from models.requisicoes import Requisicao
from models.robos_do_user import RoboDoUser
from models.contas import Conta
from services.cache_service import cache_service
from config import settings

logger = logging.getLogger(__name__)

class RequisicaoService:
    
    def __init__(self, db: Session):
        self.db = db
        self.cache = cache_service
    
    def criar_requisicao(self, requisicao_data: dict, user_id: int) -> Requisicao:
        """
        Cria uma nova requisição seguindo o fluxo de aprovação + cache
        """
        try:
            # 1. Validar dados da requisição
            if not requisicao_data.get('id_robo'):
                raise ValueError("id_robo é obrigatório")
            
            # 2. Buscar robôs operacionais
            robos_operacionais = self.db.query(RoboDoUser).filter(
                and_(
                    RoboDoUser.id_robo == requisicao_data['id_robo'],
                    RoboDoUser.ligado == True,
                    RoboDoUser.ativo == True,
                    RoboDoUser.status == "ativo"
                )
            ).all()
            
            if not robos_operacionais:
                raise ValueError("Nenhum robô operacional encontrado")
            
            # 3. Extrair IDs de contas
            ids_contas = [robo.id_conta for robo in robos_operacionais if robo.id_conta]
            
            if not ids_contas:
                raise ValueError("Nenhuma conta vinculada aos robôs operacionais")
            
            # 4. Criar requisição com aprovado = False (conforme conhecimento)
            nova_requisicao = Requisicao(
                tipo=requisicao_data['tipo'],
                comentario_ordem=requisicao_data.get('comentario_ordem'),
                symbol=requisicao_data.get('symbol'),
                quantidade=requisicao_data.get('quantidade'),
                preco=requisicao_data.get('preco'),
                id_robo=requisicao_data['id_robo'],
                ids_contas=ids_contas,
                aprovado=False,  # ✅ Inicia como False
                criado_por=user_id
            )
            
            self.db.add(nova_requisicao)
            self.db.flush()  # Para obter o ID sem commit
            
            # 5. Atualizar robôs para indicar que têm requisição
            for robo in robos_operacionais:
                robo.tem_requisicao = True
                robo.atualizado_por = user_id
            
            # 6. Iniciar processo de cache (aprovado ainda é False)
            self._processar_cache_requisicao(nova_requisicao)
            
            # 7. Commit da transação
            self.db.commit()
            self.db.refresh(nova_requisicao)
            
            logger.info(f"Requisição {nova_requisicao.id} criada com sucesso")
            return nova_requisicao
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Erro ao criar requisição: {str(e)}")
            raise
    
    def _processar_cache_requisicao(self, requisicao: Requisicao):
        """
        Processa o cache da requisição conforme especificação do conhecimento
        """
        try:
            requisicao_id = requisicao.id
            
            # 1. Preparar JSON da requisição
            requisicao_json = {
                "id": requisicao.id,
                "tipo": requisicao.tipo,
                "comentario_ordem": requisicao.comentario_ordem,
                "symbol": requisicao.symbol,
                "quantidade": float(requisicao.quantidade) if requisicao.quantidade else None,
                "preco": float(requisicao.preco) if requisicao.preco else None,
                "id_robo": requisicao.id_robo,
                "ids_contas": requisicao.ids_contas,
                "criado_em": requisicao.criado_em.isoformat(),
                "aprovado": requisicao.aprovado
            }
            
            # 2. Armazenar JSON da requisição no Redis
            cache_key_json = f"requisicao:{requisicao_id}:data"
            self.cache.set(cache_key_json, requisicao_json, ttl=3600)  # 1 hora
            
            # 3. Criar SET de contas da requisição
            cache_key_contas = f"requisicao:{requisicao_id}:contas"
            if requisicao.ids_contas:
                # Redis SET com IDs das contas
                for conta_id in requisicao.ids_contas:
                    self.cache.redis_client.sadd(cache_key_contas, conta_id)
                self.cache.redis_client.expire(cache_key_contas, 3600)
            
            # 4. Criar SETs de requisições por conta
            if requisicao.ids_contas:
                for conta_id in requisicao.ids_contas:
                    cache_key_por_conta = f"conta:{conta_id}:requisicoes"
                    self.cache.redis_client.sadd(cache_key_por_conta, requisicao_id)
                    self.cache.redis_client.expire(cache_key_por_conta, 3600)
            
            # 5. ✅ SOMENTE APÓS todas as estruturas estarem prontas, marcar como aprovado
            requisicao.aprovado = True
            requisicao.atualizado_por = requisicao.criado_por
            
            # 6. Sinalizar que a requisição está pronta para consumo
            cache_key_ready = f"requisicao:{requisicao_id}:ready"
            self.cache.set(cache_key_ready, True, ttl=3600)
            
            logger.info(f"Cache da requisição {requisicao_id} processado com sucesso")
            
        except Exception as e:
            logger.error(f"Erro ao processar cache da requisição {requisicao.id}: {str(e)}")
            # Manter aprovado = False em caso de erro
            requisicao.aprovado = False
            raise
    
    def obter_requisicao_do_cache(self, requisicao_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtém requisição do cache Redis
        """
        try:
            # Verificar se está pronta para consumo
            cache_key_ready = f"requisicao:{requisicao_id}:ready"
            if not self.cache.get(cache_key_ready):
                return None
            
            # Obter dados da requisição
            cache_key_json = f"requisicao:{requisicao_id}:data"
            return self.cache.get(cache_key_json)
            
        except Exception as e:
            logger.error(f"Erro ao obter requisição {requisicao_id} do cache: {str(e)}")
            return None
    
    def obter_contas_da_requisicao(self, requisicao_id: int) -> List[int]:
        """
        Obtém IDs das contas de uma requisição do cache
        """
        try:
            cache_key_contas = f"requisicao:{requisicao_id}:contas"
            if self.cache.redis_client:
                contas_ids = self.cache.redis_client.smembers(cache_key_contas)
                return [int(conta_id) for conta_id in contas_ids]
            return []
            
        except Exception as e:
            logger.error(f"Erro ao obter contas da requisição {requisicao_id}: {str(e)}")
            return []
    
    def obter_requisicoes_por_conta(self, conta_id: int) -> List[int]:
        """
        Obtém IDs das requisições de uma conta do cache
        """
        try:
            cache_key_por_conta = f"conta:{conta_id}:requisicoes"
            if self.cache.redis_client:
                requisicoes_ids = self.cache.redis_client.smembers(cache_key_por_conta)
                return [int(req_id) for req_id in requisicoes_ids]
            return []
            
        except Exception as e:
            logger.error(f"Erro ao obter requisições da conta {conta_id}: {str(e)}")
            return []
    
    def listar_requisicoes_aprovadas(self) -> List[Requisicao]:
        """
        Lista apenas requisições aprovadas (prontas para consumo)
        """
        return self.db.query(Requisicao).filter(Requisicao.aprovado == True).all()
    
    def invalidar_cache_requisicao(self, requisicao_id: int):
        """
        Invalida todo o cache relacionado a uma requisição
        """
        try:
            # Obter dados da requisição para limpar cache por conta
            requisicao = self.db.query(Requisicao).filter(Requisicao.id == requisicao_id).first()
            
            if requisicao and requisicao.ids_contas:
                # Limpar SETs de requisições por conta
                for conta_id in requisicao.ids_contas:
                    cache_key_por_conta = f"conta:{conta_id}:requisicoes"
                    if self.cache.redis_client:
                        self.cache.redis_client.srem(cache_key_por_conta, requisicao_id)
            
            # Limpar cache da requisição
            pattern = f"requisicao:{requisicao_id}:*"
            self.cache.clear_pattern(pattern)
            
            logger.info(f"Cache da requisição {requisicao_id} invalidado")
            
        except Exception as e:
            logger.error(f"Erro ao invalidar cache da requisição {requisicao_id}: {str(e)}")

