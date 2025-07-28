"""
Serviço de auditoria para rastreamento de mudanças e compliance
"""
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

class AuditoriaService:
    
    def __init__(self, db: Session):
        self.db = db
    
    def registrar_alteracao(self, 
                          tabela: str, 
                          registro_id: int, 
                          operacao: str,  # CREATE, UPDATE, DELETE
                          dados_anteriores: Optional[Dict[str, Any]] = None,
                          dados_novos: Optional[Dict[str, Any]] = None,
                          user_id: Optional[int] = None,
                          observacoes: Optional[str] = None):
        """
        Registra uma alteração no log de auditoria
        """
        try:
            # Criar entrada de auditoria
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "tabela": tabela,
                "registro_id": registro_id,
                "operacao": operacao,
                "user_id": user_id,
                "dados_anteriores": dados_anteriores,
                "dados_novos": dados_novos,
                "observacoes": observacoes,
                "ip_address": None,  # Pode ser adicionado via middleware
                "user_agent": None   # Pode ser adicionado via middleware
            }
            
            # Log estruturado
            logger.info(f"AUDITORIA: {operacao} em {tabela}#{registro_id} por user#{user_id}", 
                       extra={"audit_log": log_entry})
            
            # Aqui poderia ser salvo em uma tabela de auditoria específica
            # Por enquanto, usando apenas logs estruturados
            
        except Exception as e:
            logger.error(f"Erro ao registrar auditoria: {str(e)}")
    
    def registrar_login(self, user_id: int, sucesso: bool, ip_address: str = None, user_agent: str = None):
        """
        Registra tentativa de login
        """
        try:
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "evento": "LOGIN",
                "user_id": user_id,
                "sucesso": sucesso,
                "ip_address": ip_address,
                "user_agent": user_agent
            }
            
            level = logging.INFO if sucesso else logging.WARNING
            logger.log(level, f"LOGIN {'SUCESSO' if sucesso else 'FALHA'} para user#{user_id}", 
                      extra={"security_log": log_entry})
            
        except Exception as e:
            logger.error(f"Erro ao registrar login: {str(e)}")
    
    def registrar_acesso_dados_sensíveis(self, user_id: int, recurso: str, dados_acessados: str):
        """
        Registra acesso a dados sensíveis (contas, ordens, etc.)
        """
        try:
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "evento": "ACESSO_DADOS_SENSÍVEIS",
                "user_id": user_id,
                "recurso": recurso,
                "dados_acessados": dados_acessados
            }
            
            logger.info(f"ACESSO SENSÍVEL: user#{user_id} acessou {recurso}", 
                       extra={"security_log": log_entry})
            
        except Exception as e:
            logger.error(f"Erro ao registrar acesso a dados sensíveis: {str(e)}")
    
    def registrar_operacao_financeira(self, user_id: int, tipo_operacao: str, detalhes: Dict[str, Any]):
        """
        Registra operações financeiras para compliance
        """
        try:
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "evento": "OPERACAO_FINANCEIRA",
                "user_id": user_id,
                "tipo_operacao": tipo_operacao,
                "detalhes": detalhes
            }
            
            logger.info(f"OPERAÇÃO FINANCEIRA: {tipo_operacao} por user#{user_id}", 
                       extra={"compliance_log": log_entry})
            
        except Exception as e:
            logger.error(f"Erro ao registrar operação financeira: {str(e)}")
    
    def obter_historico_alteracoes(self, tabela: str, registro_id: int) -> List[Dict[str, Any]]:
        """
        Obtém histórico de alterações de um registro específico
        """
        # Esta implementação seria expandida com uma tabela de auditoria real
        # Por enquanto, retorna lista vazia
        return []
    
    def obter_atividades_usuario(self, user_id: int, data_inicio: datetime = None, data_fim: datetime = None) -> List[Dict[str, Any]]:
        """
        Obtém todas as atividades de um usuário em um período
        """
        # Esta implementação seria expandida com consultas aos logs
        # Por enquanto, retorna lista vazia
        return []
    
    def gerar_relatorio_compliance(self, data_inicio: datetime, data_fim: datetime) -> Dict[str, Any]:
        """
        Gera relatório de compliance para um período
        """
        try:
            # Consultas para estatísticas de compliance
            relatorio = {
                "periodo": {
                    "inicio": data_inicio.isoformat(),
                    "fim": data_fim.isoformat()
                },
                "estatisticas": {
                    "total_logins": 0,
                    "logins_falhados": 0,
                    "operacoes_financeiras": 0,
                    "acessos_dados_sensíveis": 0,
                    "alteracoes_registros": 0
                },
                "usuarios_mais_ativos": [],
                "operacoes_suspeitas": [],
                "recomendacoes": []
            }
            
            # Aqui seriam feitas consultas reais aos logs/tabelas de auditoria
            
            return relatorio
            
        except Exception as e:
            logger.error(f"Erro ao gerar relatório de compliance: {str(e)}")
            return {}

# Decorator para auditoria automática
def auditar_alteracao(tabela: str, operacao: str):
    """
    Decorator para auditar alterações automaticamente
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                # Executar função original
                resultado = func(*args, **kwargs)
                
                # Registrar auditoria (implementação simplificada)
                # Em uma implementação real, capturaria dados antes/depois
                logger.info(f"AUDITORIA AUTO: {operacao} em {tabela}")
                
                return resultado
                
            except Exception as e:
                logger.error(f"Erro na função auditada {func.__name__}: {str(e)}")
                raise
        
        return wrapper
    return decorator

