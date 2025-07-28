"""
Serviço de cache usando Redis
"""
import json
import redis
from typing import Any, Optional
from functools import wraps
from config import settings
import logging

logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self):
        self.redis_client = None
        if settings.REDIS_URL:
            try:
                self.redis_client = redis.from_url(settings.REDIS_URL)
                # Testar conexão
                self.redis_client.ping()
                logger.info("Redis conectado com sucesso")
            except Exception as e:
                logger.warning(f"Não foi possível conectar ao Redis: {e}")
                self.redis_client = None
        else:
            logger.info("Redis não configurado, cache desabilitado")
    
    def get(self, key: str) -> Optional[Any]:
        """Buscar valor do cache"""
        if not self.redis_client:
            return None
        
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
        except Exception as e:
            logger.error(f"Erro ao buscar cache {key}: {e}")
        
        return None
    
    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Armazenar valor no cache"""
        if not self.redis_client:
            return False
        
        try:
            ttl = ttl or settings.CACHE_TTL
            serialized_value = json.dumps(value, default=str)
            self.redis_client.setex(key, ttl, serialized_value)
            return True
        except Exception as e:
            logger.error(f"Erro ao armazenar cache {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Remover valor do cache"""
        if not self.redis_client:
            return False
        
        try:
            self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Erro ao remover cache {key}: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> bool:
        """Limpar chaves que correspondem ao padrão"""
        if not self.redis_client:
            return False
        
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
            return True
        except Exception as e:
            logger.error(f"Erro ao limpar cache com padrão {pattern}: {e}")
            return False

# Instância global do cache
cache_service = CacheService()

def cache_result(key_prefix: str = "", ttl: int = None):
    """Decorator para cachear resultados de funções"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Gerar chave do cache
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            # Tentar buscar do cache
            cached_result = cache_service.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit para {cache_key}")
                return cached_result
            
            # Executar função e cachear resultado
            result = await func(*args, **kwargs)
            cache_service.set(cache_key, result, ttl)
            logger.debug(f"Cache miss para {cache_key}, resultado armazenado")
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Gerar chave do cache
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            # Tentar buscar do cache
            cached_result = cache_service.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit para {cache_key}")
                return cached_result
            
            # Executar função e cachear resultado
            result = func(*args, **kwargs)
            cache_service.set(cache_key, result, ttl)
            logger.debug(f"Cache miss para {cache_key}, resultado armazenado")
            
            return result
        
        # Retornar wrapper apropriado baseado na função
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

