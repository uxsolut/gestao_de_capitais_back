# Projeto de Gestão de Capitais - Versão 5.0

## 🚀 Visão Geral

A versão 5.0 representa uma evolução significativa do sistema de gestão de capitais, com foco em:

- **Fluxo de Aprovação Inteligente**: Implementação completa do sistema de aprovação de requisições com cache Redis
- **Auditoria Completa**: Rastreamento de todas as operações para compliance financeiro
- **Arquitetura Aprimorada**: Correção de relacionamentos circulares e inconsistências
- **Services Especializados**: Camada de serviços robusta para lógica de negócio
- **Integridade de Dados**: Campos de auditoria e validações rigorosas

## 📋 Pré-requisitos

- Python 3.11+
- PostgreSQL 12+
- Redis 6+
- FastAPI
- SQLAlchemy
- Pydantic

## 🔧 Instalação

### 1. Clonar o Projeto
```bash
git clone <repository-url>
cd projeto_v5
```

### 2. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 3. Configurar Variáveis de Ambiente
```bash
# Copiar arquivo de exemplo
cp .env.example .env

# Editar configurações
nano .env
```

**Variáveis Obrigatórias:**
```bash
# Banco de Dados
DATABASE_URL=postgresql://user:password@localhost/dbname

# Redis (CRÍTICO para v5.0)
REDIS_URL=redis://localhost:6379/0

# Segurança
SECRET_KEY=sua_chave_secreta_muito_segura
CORS_ORIGINS=http://localhost:3000,http://localhost:56166

# Auditoria
ENABLE_AUDIT_LOGS=true
AUDIT_LOG_LEVEL=INFO
COMPLIANCE_MODE=true
```

### 4. Migração do Banco de Dados

⚠️ **ATENÇÃO**: Esta é uma migração com BREAKING CHANGES. Faça backup antes!

```bash
# Backup do banco atual
pg_dump -h localhost -U username -d database_name > backup_pre_v5.sql

# Executar migração
psql -h localhost -U username -d database_name < MIGRATION_SCRIPT.sql
```

### 5. Iniciar Serviços

```bash
# Iniciar Redis
redis-server

# Iniciar aplicação
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 🏗️ Arquitetura

### Estrutura de Diretórios
```
projeto_v5/
├── models/              # Modelos de dados (SQLAlchemy)
│   ├── users.py
│   ├── requisicoes.py
│   ├── ordens.py
│   ├── contas.py
│   ├── robos.py
│   └── ...
├── schemas/             # Esquemas de validação (Pydantic)
│   ├── users.py
│   ├── requisicoes.py
│   └── ...
├── routers/             # Endpoints da API
│   ├── users.py
│   ├── requisicoes.py
│   └── ...
├── services/            # Lógica de negócio
│   ├── requisicao_service.py
│   ├── auditoria_service.py
│   └── cache_service.py
├── auth/                # Autenticação e autorização
├── middleware/          # Middlewares customizados
└── tests/               # Testes automatizados
```

### Fluxo de Dados

```mermaid
graph TD
    A[Cliente] --> B[Router]
    B --> C[Service Layer]
    C --> D[Model/Database]
    C --> E[Cache Redis]
    C --> F[Auditoria]
    
    G[Requisição] --> H[aprovado=false]
    H --> I[Processar Cache]
    I --> J[Cache Completo?]
    J -->|Sim| K[aprovado=true]
    J -->|Não| L[Manter false]
```

## 🔄 Principais Mudanças da v5.0

### ✅ Fluxo de Aprovação de Requisições

O sistema agora implementa o fluxo completo conforme especificação:

1. **Criação**: Requisição criada com `aprovado = false`
2. **Cache**: Dados processados no Redis (JSON + SETs)
3. **Aprovação**: Apenas após cache completo, `aprovado = true`
4. **Consumo**: Requisição disponível para consumo

```python
# Exemplo de uso
requisicao_service = RequisicaoService(db)
nova_requisicao = requisicao_service.criar_requisicao(dados, user_id)

# Verificar se está pronta para consumo
dados_cache = requisicao_service.obter_requisicao_do_cache(requisicao.id)
```

### ✅ Sistema de Auditoria

Todas as operações são auditadas automaticamente:

```python
# Auditoria automática em todas as operações
auditoria_service = AuditoriaService(db)
auditoria_service.registrar_alteracao(
    tabela="requisicoes",
    registro_id=requisicao.id,
    operacao="CREATE",
    user_id=current_user.id
)
```

### ✅ Models Aprimorados

- **Campos de Auditoria**: `criado_em`, `atualizado_em`, `criado_por`, `atualizado_por`
- **Relacionamentos Corrigidos**: Eliminação de referências circulares
- **Validações Rigorosas**: Constraints e tipos de dados otimizados
- **Métodos Utilitários**: Properties e métodos para lógica de negócio

## 📚 API Endpoints

### Requisições
```
POST   /requisicoes/              # Criar requisição
GET    /requisicoes/              # Listar com filtros
GET    /requisicoes/{id}          # Obter específica
PUT    /requisicoes/{id}          # Atualizar
GET    /requisicoes/{id}/cache    # Obter do cache
GET    /requisicoes/aprovadas/    # Listar aprovadas
```

### Usuários
```
POST   /users/                    # Criar usuário
POST   /users/login               # Login
GET    /users/                    # Listar usuários
```

### Outros Endpoints
- `/ordens/` - Gerenciamento de ordens
- `/contas/` - Gerenciamento de contas
- `/robos/` - Gerenciamento de robôs
- `/carteiras/` - Gerenciamento de carteiras

## 🧪 Testes

```bash
# Executar todos os testes
pytest

# Testes com cobertura
pytest --cov=.

# Testes específicos
pytest tests/test_requisicoes.py
```

## 📊 Monitoramento

### Logs Estruturados
```python
# Logs de auditoria
logger.info("AUDITORIA: CREATE em requisicoes#123 por user#456", 
           extra={"audit_log": log_entry})

# Logs de segurança
logger.warning("LOGIN FALHA para user#123", 
              extra={"security_log": security_entry})
```

### Métricas Redis
```bash
# Monitorar cache
redis-cli info memory
redis-cli info stats

# Verificar chaves de requisições
redis-cli keys "requisicao:*"
```

## 🔒 Segurança

### Controle de Acesso
- Autenticação JWT obrigatória
- Permissões granulares por usuário
- Isolamento de dados por conta/carteira
- Auditoria de todos os acessos

### Validações
- Validação rigorosa de entrada
- Sanitização de dados
- Verificação de integridade referencial
- Rate limiting (recomendado implementar)

## 🚨 Troubleshooting

### Problemas Comuns

**1. Erro de Migração**
```bash
# Verificar dados inconsistentes antes da migração
psql -d database_name -f pre_migration_checks.sql
```

**2. Redis Indisponível**
```python
# Sistema funciona com fallback gracioso
# Verificar logs para warnings sobre cache
```

**3. Relacionamentos Quebrados**
```sql
-- Verificar integridade
SELECT COUNT(*) FROM ordens o 
LEFT JOIN robos_do_user ru ON o.id_robo_user = ru.id 
WHERE o.id_robo_user IS NOT NULL AND ru.id IS NULL;
```

### Logs Importantes
```bash
# Logs de aplicação
tail -f logs/app.log

# Logs de auditoria
grep "AUDITORIA" logs/app.log

# Logs de segurança
grep "LOGIN\|ACESSO" logs/app.log
```

## 📈 Performance

### Otimizações Implementadas
- Cache Redis para requisições frequentes
- Índices otimizados para consultas
- Consultas SQL otimizadas
- Paginação em listagens

### Métricas Esperadas
- Tempo de resposta: < 200ms (95% das requisições)
- Cache hit rate: > 80%
- Throughput: > 1000 req/s
- Disponibilidade: > 99.9%

## 🔄 Rollback

Em caso de problemas críticos:

```bash
# 1. Parar aplicação
systemctl stop your-app-service

# 2. Restaurar backup
psql -h localhost -U username -d database_name < backup_pre_v5.sql

# 3. Reverter código
git checkout v2.0

# 4. Reiniciar
systemctl start your-app-service
```

## 📞 Suporte

- **Documentação**: Consulte `CHANGELOG_V5.md` para detalhes técnicos
- **Issues**: Reporte problemas no sistema de issues
- **Migração**: Suporte especializado disponível para migração

## 🎯 Roadmap

### Próximas Versões
- [ ] Tabela de auditoria dedicada
- [ ] Dashboard de compliance
- [ ] Alertas automáticos de segurança
- [ ] Cache distribuído
- [ ] Testes de carga automatizados

---

**Versão:** 5.0  
**Data:** 26/07/2025  
**Autor:** Manus AI  
**Status:** Produção Ready

