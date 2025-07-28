# Changelog - Versão 5.0

**Data de Release:** 26 de julho de 2025  
**Versão Anterior:** 2.0  
**Tipo de Release:** Major Update  

## 🎯 Resumo das Mudanças

A versão 5.0 representa uma evolução significativa na arquitetura de dados e serviços, com foco em:
- Implementação do fluxo de aprovação de requisições com cache Redis
- Adição de campos de auditoria em todos os models
- Correção de relacionamentos circulares e inconsistências
- Criação de services especializados para lógica de negócio
- Melhoria na integridade e consistência dos dados

## 🔄 Alterações nos Models

### ✅ Requisicao (BREAKING CHANGES)
**Arquivo:** `models/requisicoes.py`

**Campos Adicionados:**
- `aprovado: Boolean` - Campo crítico para controle de fluxo de cache
- `criado_em: DateTime` - Timestamp de criação (já existia, mantido)
- `atualizado_em: DateTime` - Timestamp de última atualização
- `criado_por: Integer` - FK para users.id (quem criou)
- `atualizado_por: Integer` - FK para users.id (quem atualizou)

**Relacionamentos Melhorados:**
- `robo: relationship("Robos")` - Relacionamento bidirecional
- `criador: relationship("User")` - Usuário que criou
- `atualizador: relationship("User")` - Usuário que atualizou

**Métodos Adicionados:**
- `__repr__()` - Representação string melhorada

### ✅ RobosDoUser (BREAKING CHANGES)
**Arquivo:** `models/robos_do_user.py`

**Campos Adicionados:**
- `status: String(20)` - Status geral (inativo, ativo, pausado, erro)
- `criado_em: DateTime` - Timestamp de criação
- `atualizado_em: DateTime` - Timestamp de atualização
- `criado_por: Integer` - FK para users.id
- `atualizado_por: Integer` - FK para users.id

**Campos Removidos:**
- `id_ordem: Integer` - Removido relacionamento circular com Ordem

**Relacionamentos Corrigidos:**
- Removido relacionamento circular com `Ordem`
- Adicionados relacionamentos de auditoria

**Métodos Adicionados:**
- `is_operacional` - Property para verificar se robô está operacional
- `__repr__()` - Representação string melhorada

### ✅ Ordem (BREAKING CHANGES)
**Arquivo:** `models/ordens.py`

**Campos Modificados:**
- `numero_unico: String` - Adicionado constraint UNIQUE
- `quantidade: Numeric(15, 4)` - Maior precisão
- `preco: Numeric(15, 8)` - Maior precisão para preços
- `status: String(20)` - Status da ordem (pendente, executada, cancelada, rejeitada)

**Campos Adicionados:**
- `id_conta: Integer` - FK direta para contas.id
- `executado_em: DateTime` - Timestamp de execução
- `criado_em: DateTime` - Timestamp de criação (já existia, mantido)
- `atualizado_em: DateTime` - Timestamp de atualização
- `criado_por: Integer` - FK para users.id
- `atualizado_por: Integer` - FK para users.id

**Relacionamentos Simplificados:**
- Removido relacionamento circular com `RobosDoUser`
- Adicionado relacionamento direto com `Conta`

**Métodos Adicionados:**
- `valor_total` - Property para calcular valor total
- `is_executada` - Property para verificar se foi executada
- `__repr__()` - Representação string melhorada

### ✅ Conta (BREAKING CHANGES)
**Arquivo:** `models/contas.py`

**Campos Modificados:**
- `nome: String` - Agora obrigatório (nullable=False)
- `conta_meta_trader: String` - Adicionado constraint UNIQUE
- `margem_total: Numeric(15, 2)` - Precisão padronizada
- `margem_disponivel: Numeric(15, 2)` - Precisão padronizada

**Campos Adicionados:**
- `margem_utilizada: Numeric(15, 2)` - Campo para controle de margem
- `ativa: Boolean` - Status ativo/inativo
- `status: String(20)` - Status detalhado (ativa, inativa, bloqueada, suspensa)
- `criado_em: DateTime` - Timestamp de criação
- `atualizado_em: DateTime` - Timestamp de atualização
- `criado_por: Integer` - FK para users.id
- `atualizado_por: Integer` - FK para users.id

**Relacionamentos Adicionados:**
- `ordens: relationship("Ordem")` - Relacionamento com ordens
- Relacionamentos de auditoria

**Métodos Adicionados:**
- `margem_livre` - Property para calcular margem livre
- `percentual_utilizacao` - Property para percentual de utilização
- `pode_operar(valor)` - Método para verificar se pode operar
- `__repr__()` - Representação string melhorada

### ✅ User (BREAKING CHANGES)
**Arquivo:** `models/users.py`

**Campos Modificados:**
- `cpf: String` - Adicionado constraint UNIQUE
- `tipo_de_user: String` - Agora obrigatório com default "cliente"

**Campos Removidos:**
- `id_conta: Integer` - Removido relacionamento direto com conta

**Campos Adicionados:**
- `ativo: Boolean` - Status ativo/inativo
- `email_verificado: Boolean` - Status de verificação de email
- `ultimo_login: DateTime` - Timestamp do último login
- `criado_em: DateTime` - Timestamp de criação
- `atualizado_em: DateTime` - Timestamp de atualização
- `criado_por: Integer` - FK para users.id (auto-referência)
- `atualizado_por: Integer` - FK para users.id (auto-referência)

**Relacionamentos Corrigidos:**
- Removido `id_conta` direto, agora via carteiras
- Adicionados relacionamentos de auditoria
- Adicionados relacionamentos reversos para auditoria

**Métodos Adicionados:**
- `is_admin` - Property para verificar se é admin
- `is_ativo` - Property para verificar se está ativo
- `pode_operar()` - Método para verificar se pode operar
- `get_contas_ativas()` - Método para obter contas ativas
- `__repr__()` - Representação string melhorada

### ✅ Robos (MINOR CHANGES)
**Arquivo:** `models/robos.py`

**Campos Adicionados:**
- `ativo: Boolean` - Status ativo/inativo
- `versao: String` - Versão do robô
- `tipo: String` - Tipo de robô (scalper, swing, etc.)
- `criado_em: DateTime` - Timestamp de criação
- `atualizado_em: DateTime` - Timestamp de atualização
- `criado_por: Integer` - FK para users.id
- `atualizado_por: Integer` - FK para users.id

**Relacionamentos Adicionados:**
- `requisicoes: relationship("Requisicao")` - Relacionamento com requisições
- Relacionamentos de auditoria

**Métodos Adicionados:**
- `usuarios_ativos` - Property para contar usuários ativos
- `get_requisicoes_pendentes()` - Método para obter requisições pendentes
- `__repr__()` - Representação string melhorada


## 🔧 Novos Services

### ✅ RequisicaoService (NOVO)
**Arquivo:** `services/requisicao_service.py`

**Funcionalidades:**
- `criar_requisicao()` - Cria requisição com fluxo de aprovação completo
- `_processar_cache_requisicao()` - Implementa lógica de cache conforme especificação
- `obter_requisicao_do_cache()` - Obtém requisição do cache Redis
- `obter_contas_da_requisicao()` - Obtém contas de uma requisição do cache
- `obter_requisicoes_por_conta()` - Obtém requisições de uma conta do cache
- `listar_requisicoes_aprovadas()` - Lista apenas requisições aprovadas
- `invalidar_cache_requisicao()` - Invalida cache de uma requisição

**Implementação do Fluxo de Aprovação:**
1. Requisição criada com `aprovado = False`
2. Cache preenchido no Redis (JSON + SETs)
3. Apenas após cache completo, `aprovado = True`
4. Sinalização de "ready" no Redis

### ✅ AuditoriaService (NOVO)
**Arquivo:** `services/auditoria_service.py`

**Funcionalidades:**
- `registrar_alteracao()` - Registra mudanças em registros
- `registrar_login()` - Registra tentativas de login
- `registrar_acesso_dados_sensíveis()` - Registra acessos a dados críticos
- `registrar_operacao_financeira()` - Registra operações financeiras
- `obter_historico_alteracoes()` - Obtém histórico de um registro
- `obter_atividades_usuario()` - Obtém atividades de um usuário
- `gerar_relatorio_compliance()` - Gera relatório de compliance

**Decorator de Auditoria:**
- `@auditar_alteracao()` - Decorator para auditoria automática

## 📊 Alterações nos Schemas

### ✅ RequisicaoCreate (ENHANCED)
**Arquivo:** `schemas/requisicoes.py`

**Validações Adicionadas:**
- Validação de tipos de requisição permitidos
- Validação de symbol (uppercase automático)
- Validação de valores positivos para quantidade e preço

### ✅ RequisicaoUpdate (NOVO)
**Schema para atualizações parciais de requisições**

### ✅ RequisicaoDetalhada (NOVO)
**Schema com informações de relacionamentos incluídas**

### ✅ RequisicaoCache (NOVO)
**Schema específico para dados em cache Redis**

## 🔄 Alterações nos Routers

### ✅ RequisicaoRouter (MAJOR REFACTOR)
**Arquivo:** `routers/requisicoes.py`

**Endpoints Novos/Modificados:**
- `POST /requisicoes/` - Usa RequisicaoService para criação
- `GET /requisicoes/` - Filtros avançados e paginação
- `GET /requisicoes/{id}` - Controle de permissões melhorado
- `PUT /requisicoes/{id}` - Atualização com auditoria
- `GET /requisicoes/{id}/cache` - Acesso direto ao cache
- `GET /requisicoes/aprovadas/` - Lista apenas aprovadas

**Melhorias:**
- Integração com services especializados
- Auditoria automática de todas as operações
- Controle de permissões granular
- Tratamento de erros padronizado
- Validações de negócio

## 🗄️ Migrações de Banco de Dados

### Campos Adicionados (Requer ALTER TABLE):

**Tabela `requisicoes`:**
```sql
ALTER TABLE requisicoes ADD COLUMN aprovado BOOLEAN DEFAULT FALSE NOT NULL;
ALTER TABLE requisicoes ADD COLUMN atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE requisicoes ADD COLUMN criado_por INTEGER REFERENCES users(id);
ALTER TABLE requisicoes ADD COLUMN atualizado_por INTEGER REFERENCES users(id);
```

**Tabela `robos_do_user`:**
```sql
ALTER TABLE robos_do_user ADD COLUMN status VARCHAR(20) DEFAULT 'inativo' NOT NULL;
ALTER TABLE robos_do_user ADD COLUMN criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;
ALTER TABLE robos_do_user ADD COLUMN atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE robos_do_user ADD COLUMN criado_por INTEGER REFERENCES users(id);
ALTER TABLE robos_do_user ADD COLUMN atualizado_por INTEGER REFERENCES users(id);
ALTER TABLE robos_do_user DROP COLUMN id_ordem; -- BREAKING CHANGE
```

**Tabela `ordens`:**
```sql
ALTER TABLE ordens ADD CONSTRAINT ordens_numero_unico_unique UNIQUE (numero_unico);
ALTER TABLE ordens ALTER COLUMN quantidade TYPE NUMERIC(15,4);
ALTER TABLE ordens ALTER COLUMN preco TYPE NUMERIC(15,8);
ALTER TABLE ordens ADD COLUMN status VARCHAR(20) DEFAULT 'pendente' NOT NULL;
ALTER TABLE ordens ADD COLUMN id_conta INTEGER REFERENCES contas(id);
ALTER TABLE ordens ADD COLUMN executado_em TIMESTAMP;
ALTER TABLE ordens ADD COLUMN atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE ordens ADD COLUMN criado_por INTEGER REFERENCES users(id);
ALTER TABLE ordens ADD COLUMN atualizado_por INTEGER REFERENCES users(id);
```

**Tabela `contas`:**
```sql
ALTER TABLE contas ALTER COLUMN nome SET NOT NULL;
ALTER TABLE contas ADD CONSTRAINT contas_meta_trader_unique UNIQUE (conta_meta_trader);
ALTER TABLE contas ALTER COLUMN margem_total TYPE NUMERIC(15,2);
ALTER TABLE contas ALTER COLUMN margem_disponivel TYPE NUMERIC(15,2);
ALTER TABLE contas ADD COLUMN margem_utilizada NUMERIC(15,2) DEFAULT 0.00;
ALTER TABLE contas ADD COLUMN ativa BOOLEAN DEFAULT TRUE NOT NULL;
ALTER TABLE contas ADD COLUMN status VARCHAR(20) DEFAULT 'ativa' NOT NULL;
ALTER TABLE contas ADD COLUMN criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;
ALTER TABLE contas ADD COLUMN atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE contas ADD COLUMN criado_por INTEGER REFERENCES users(id);
ALTER TABLE contas ADD COLUMN atualizado_por INTEGER REFERENCES users(id);
```

**Tabela `users`:**
```sql
ALTER TABLE users ADD CONSTRAINT users_cpf_unique UNIQUE (cpf);
ALTER TABLE users ALTER COLUMN tipo_de_user SET NOT NULL;
ALTER TABLE users ALTER COLUMN tipo_de_user SET DEFAULT 'cliente';
ALTER TABLE users DROP COLUMN id_conta; -- BREAKING CHANGE
ALTER TABLE users ADD COLUMN ativo BOOLEAN DEFAULT TRUE NOT NULL;
ALTER TABLE users ADD COLUMN email_verificado BOOLEAN DEFAULT FALSE NOT NULL;
ALTER TABLE users ADD COLUMN ultimo_login TIMESTAMP;
ALTER TABLE users ADD COLUMN criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;
ALTER TABLE users ADD COLUMN atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE users ADD COLUMN criado_por INTEGER REFERENCES users(id);
ALTER TABLE users ADD COLUMN atualizado_por INTEGER REFERENCES users(id);
```

**Tabela `robos`:**
```sql
ALTER TABLE robos ADD COLUMN ativo BOOLEAN DEFAULT TRUE NOT NULL;
ALTER TABLE robos ADD COLUMN versao VARCHAR;
ALTER TABLE robos ADD COLUMN tipo VARCHAR;
ALTER TABLE robos ADD COLUMN criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;
ALTER TABLE robos ADD COLUMN atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE robos ADD COLUMN criado_por INTEGER REFERENCES users(id);
ALTER TABLE robos ADD COLUMN atualizado_por INTEGER REFERENCES users(id);
```


## ⚠️ BREAKING CHANGES

### 1. Modelo Requisicao
- **Campo `aprovado` adicionado:** Todas as requisições existentes precisarão ser marcadas como aprovadas manualmente
- **Campos de auditoria:** Requisições existentes terão campos de auditoria NULL

### 2. Modelo RobosDoUser
- **Campo `id_ordem` removido:** Relacionamento circular eliminado
- **Campo `status` adicionado:** Robôs existentes terão status "inativo" por padrão

### 3. Modelo Ordem
- **Constraint UNIQUE em `numero_unico`:** Pode falhar se houver duplicatas
- **Tipos de dados alterados:** Maior precisão pode afetar cálculos existentes
- **Campo `id_conta` adicionado:** Ordens existentes terão NULL

### 4. Modelo Conta
- **Campo `nome` obrigatório:** Contas sem nome causarão erro
- **Constraint UNIQUE em `conta_meta_trader`:** Pode falhar se houver duplicatas

### 5. Modelo User
- **Campo `id_conta` removido:** Relacionamento direto eliminado
- **Constraint UNIQUE em `cpf`:** Pode falhar se houver duplicatas

## 📋 Guia de Migração

### Pré-Migração (OBRIGATÓRIO)

1. **Backup Completo do Banco de Dados**
```bash
pg_dump -h localhost -U username -d database_name > backup_pre_v5.sql
```

2. **Verificar Dados Inconsistentes**
```sql
-- Verificar contas sem nome
SELECT id, conta_meta_trader FROM contas WHERE nome IS NULL OR nome = '';

-- Verificar CPFs duplicados
SELECT cpf, COUNT(*) FROM users WHERE cpf IS NOT NULL GROUP BY cpf HAVING COUNT(*) > 1;

-- Verificar contas Meta Trader duplicadas
SELECT conta_meta_trader, COUNT(*) FROM contas 
WHERE conta_meta_trader IS NOT NULL 
GROUP BY conta_meta_trader HAVING COUNT(*) > 1;

-- Verificar números únicos de ordem duplicados
SELECT numero_unico, COUNT(*) FROM ordens 
WHERE numero_unico IS NOT NULL 
GROUP BY numero_unico HAVING COUNT(*) > 1;
```

3. **Limpar Dados Inconsistentes**
```sql
-- Atualizar contas sem nome
UPDATE contas SET nome = CONCAT('Conta ', id) WHERE nome IS NULL OR nome = '';

-- Remover CPFs duplicados (manter apenas o primeiro)
WITH duplicates AS (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY cpf ORDER BY id) as rn
    FROM users WHERE cpf IS NOT NULL
)
UPDATE users SET cpf = NULL WHERE id IN (
    SELECT id FROM duplicates WHERE rn > 1
);

-- Corrigir contas Meta Trader duplicadas
UPDATE contas SET conta_meta_trader = CONCAT(conta_meta_trader, '_', id) 
WHERE conta_meta_trader IN (
    SELECT conta_meta_trader FROM contas 
    WHERE conta_meta_trader IS NOT NULL 
    GROUP BY conta_meta_trader HAVING COUNT(*) > 1
);
```

### Migração Passo a Passo

1. **Parar Aplicação**
```bash
# Parar todos os serviços
systemctl stop your-app-service
systemctl stop redis-server  # Temporariamente
```

2. **Executar Migrações de Schema**
```bash
# Usar Alembic ou executar SQLs manualmente
alembic upgrade head
```

3. **Migrar Dados Existentes**
```sql
-- Marcar todas as requisições existentes como aprovadas
UPDATE requisicoes SET aprovado = TRUE WHERE aprovado IS NULL;

-- Definir status padrão para robôs
UPDATE robos_do_user SET status = 'ativo' WHERE ligado = TRUE AND ativo = TRUE;
UPDATE robos_do_user SET status = 'inativo' WHERE ligado = FALSE OR ativo = FALSE;

-- Definir status padrão para contas
UPDATE contas SET ativa = TRUE, status = 'ativa' WHERE ativa IS NULL;

-- Definir campos de usuário
UPDATE users SET ativo = TRUE, email_verificado = FALSE WHERE ativo IS NULL;
UPDATE users SET tipo_de_user = 'cliente' WHERE tipo_de_user IS NULL;
```

4. **Verificar Integridade**
```sql
-- Verificar se todas as requisições têm status de aprovação
SELECT COUNT(*) FROM requisicoes WHERE aprovado IS NULL;

-- Verificar relacionamentos
SELECT COUNT(*) FROM ordens o 
LEFT JOIN robos_do_user ru ON o.id_robo_user = ru.id 
WHERE o.id_robo_user IS NOT NULL AND ru.id IS NULL;
```

5. **Atualizar Aplicação**
```bash
# Deploy da nova versão
cp -r projeto_v5/* /path/to/production/
pip install -r requirements.txt
```

6. **Reiniciar Serviços**
```bash
systemctl start redis-server
systemctl start your-app-service
```

### Pós-Migração

1. **Testes de Funcionalidade**
- Criar nova requisição e verificar fluxo de aprovação
- Verificar cache Redis funcionando
- Testar endpoints de auditoria
- Verificar relacionamentos entre entidades

2. **Monitoramento**
- Verificar logs de aplicação
- Monitorar performance do Redis
- Verificar métricas de auditoria

3. **Rollback (Se Necessário)**
```bash
# Restaurar backup
psql -h localhost -U username -d database_name < backup_pre_v5.sql

# Reverter código
git checkout v2.0
systemctl restart your-app-service
```

## 🔧 Configurações Necessárias

### Variáveis de Ambiente Adicionais
```bash
# Cache Redis (já existente, mas crítico para v5)
REDIS_URL=redis://localhost:6379/0

# Configurações de auditoria
ENABLE_AUDIT_LOGS=true
AUDIT_LOG_LEVEL=INFO

# Configurações de compliance
COMPLIANCE_MODE=true
RETENTION_DAYS=2555  # 7 anos para dados financeiros
```

### Configuração do Redis
```bash
# Configurações recomendadas para produção
maxmemory 2gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
```

## 📈 Melhorias de Performance

### Índices Recomendados
```sql
-- Índices para auditoria
CREATE INDEX idx_requisicoes_aprovado ON requisicoes(aprovado);
CREATE INDEX idx_requisicoes_criado_em ON requisicoes(criado_em);
CREATE INDEX idx_ordens_status ON ordens(status);
CREATE INDEX idx_contas_ativa ON contas(ativa);
CREATE INDEX idx_users_ativo ON users(ativo);

-- Índices para relacionamentos
CREATE INDEX idx_requisicoes_criado_por ON requisicoes(criado_por);
CREATE INDEX idx_ordens_id_conta ON ordens(id_conta);
CREATE INDEX idx_robos_do_user_status ON robos_do_user(status);
```

### Cache Redis Otimizado
- TTL configurável por tipo de dados
- Estruturas de dados otimizadas (SETs para relacionamentos)
- Invalidação inteligente de cache
- Fallback gracioso quando Redis indisponível

## 🔒 Melhorias de Segurança

### Auditoria Completa
- Todas as operações CRUD são auditadas
- Logs estruturados para análise
- Rastreamento de acessos a dados sensíveis
- Relatórios de compliance automáticos

### Controle de Permissões
- Verificação granular de permissões
- Isolamento de dados por usuário
- Validações de negócio rigorosas
- Prevenção de acessos não autorizados

## 🎯 Próximos Passos Recomendados

1. **Implementar Tabela de Auditoria Dedicada**
   - Criar tabela `audit_logs` para persistir logs
   - Implementar retenção automática de dados

2. **Expandir Testes Automatizados**
   - Testes de integração para services
   - Testes de performance para cache
   - Testes de segurança para auditoria

3. **Monitoramento Avançado**
   - Dashboards para métricas de auditoria
   - Alertas para operações suspeitas
   - Relatórios automáticos de compliance

4. **Otimizações Adicionais**
   - Cache distribuído para múltiplas instâncias
   - Compressão de dados em cache
   - Otimização de consultas complexas

---

**Versão:** 5.0  
**Compatibilidade:** Breaking changes em relação à v2.0  
**Suporte:** Migração assistida disponível  
**Documentação:** Completa e atualizada

