-- =====================================================
-- SCRIPT DE MIGRAÇÃO PARA VERSÃO 5.0
-- Data: 26/07/2025
-- Descrição: Migração completa dos models e estruturas
-- =====================================================

-- IMPORTANTE: Execute este script em uma transação para poder fazer rollback se necessário
BEGIN;

-- =====================================================
-- 1. PRÉ-MIGRAÇÃO: LIMPEZA DE DADOS INCONSISTENTES
-- =====================================================

-- Atualizar contas sem nome
UPDATE contas SET nome = CONCAT('Conta ', id) WHERE nome IS NULL OR nome = '';

-- Remover CPFs duplicados (manter apenas o primeiro)
WITH duplicates AS (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY cpf ORDER BY id) as rn
    FROM users WHERE cpf IS NOT NULL AND cpf != ''
)
UPDATE users SET cpf = NULL WHERE id IN (
    SELECT id FROM duplicates WHERE rn > 1
);

-- Corrigir contas Meta Trader duplicadas
UPDATE contas SET conta_meta_trader = CONCAT(conta_meta_trader, '_', id) 
WHERE conta_meta_trader IN (
    SELECT conta_meta_trader FROM contas 
    WHERE conta_meta_trader IS NOT NULL AND conta_meta_trader != ''
    GROUP BY conta_meta_trader HAVING COUNT(*) > 1
);

-- Corrigir números únicos de ordem duplicados
UPDATE ordens SET numero_unico = CONCAT(numero_unico, '_', id) 
WHERE numero_unico IN (
    SELECT numero_unico FROM ordens 
    WHERE numero_unico IS NOT NULL AND numero_unico != ''
    GROUP BY numero_unico HAVING COUNT(*) > 1
);

-- =====================================================
-- 2. ALTERAÇÕES NA TABELA REQUISICOES
-- =====================================================

-- Adicionar campo aprovado
ALTER TABLE requisicoes ADD COLUMN aprovado BOOLEAN DEFAULT FALSE NOT NULL;

-- Adicionar campos de auditoria
ALTER TABLE requisicoes ADD COLUMN atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE requisicoes ADD COLUMN criado_por INTEGER;
ALTER TABLE requisicoes ADD COLUMN atualizado_por INTEGER;

-- Adicionar foreign keys de auditoria
ALTER TABLE requisicoes ADD CONSTRAINT fk_requisicoes_criado_por 
    FOREIGN KEY (criado_por) REFERENCES users(id);
ALTER TABLE requisicoes ADD CONSTRAINT fk_requisicoes_atualizado_por 
    FOREIGN KEY (atualizado_por) REFERENCES users(id);

-- Marcar todas as requisições existentes como aprovadas
UPDATE requisicoes SET aprovado = TRUE;

-- =====================================================
-- 3. ALTERAÇÕES NA TABELA ROBOS_DO_USER
-- =====================================================

-- Adicionar campo status
ALTER TABLE robos_do_user ADD COLUMN status VARCHAR(20) DEFAULT 'inativo' NOT NULL;

-- Adicionar campos de auditoria
ALTER TABLE robos_do_user ADD COLUMN criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;
ALTER TABLE robos_do_user ADD COLUMN atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE robos_do_user ADD COLUMN criado_por INTEGER;
ALTER TABLE robos_do_user ADD COLUMN atualizado_por INTEGER;

-- Adicionar foreign keys de auditoria
ALTER TABLE robos_do_user ADD CONSTRAINT fk_robos_do_user_criado_por 
    FOREIGN KEY (criado_por) REFERENCES users(id);
ALTER TABLE robos_do_user ADD CONSTRAINT fk_robos_do_user_atualizado_por 
    FOREIGN KEY (atualizado_por) REFERENCES users(id);

-- Definir status baseado nos campos existentes
UPDATE robos_do_user SET status = 'ativo' WHERE ligado = TRUE AND ativo = TRUE;
UPDATE robos_do_user SET status = 'pausado' WHERE ligado = FALSE AND ativo = TRUE;
UPDATE robos_do_user SET status = 'inativo' WHERE ativo = FALSE;

-- Remover campo id_ordem (BREAKING CHANGE)
ALTER TABLE robos_do_user DROP COLUMN IF EXISTS id_ordem;

-- =====================================================
-- 4. ALTERAÇÕES NA TABELA ORDENS
-- =====================================================

-- Adicionar constraint unique para numero_unico
ALTER TABLE ordens ADD CONSTRAINT ordens_numero_unico_unique UNIQUE (numero_unico);

-- Alterar tipos de dados para maior precisão
ALTER TABLE ordens ALTER COLUMN quantidade TYPE NUMERIC(15,4);
ALTER TABLE ordens ALTER COLUMN preco TYPE NUMERIC(15,8);

-- Adicionar campo status
ALTER TABLE ordens ADD COLUMN status VARCHAR(20) DEFAULT 'pendente' NOT NULL;

-- Adicionar relacionamento direto com conta
ALTER TABLE ordens ADD COLUMN id_conta INTEGER;
ALTER TABLE ordens ADD CONSTRAINT fk_ordens_id_conta 
    FOREIGN KEY (id_conta) REFERENCES contas(id);

-- Adicionar campos de auditoria
ALTER TABLE ordens ADD COLUMN executado_em TIMESTAMP;
ALTER TABLE ordens ADD COLUMN atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE ordens ADD COLUMN criado_por INTEGER;
ALTER TABLE ordens ADD COLUMN atualizado_por INTEGER;

-- Adicionar foreign keys de auditoria
ALTER TABLE ordens ADD CONSTRAINT fk_ordens_criado_por 
    FOREIGN KEY (criado_por) REFERENCES users(id);
ALTER TABLE ordens ADD CONSTRAINT fk_ordens_atualizado_por 
    FOREIGN KEY (atualizado_por) REFERENCES users(id);

-- =====================================================
-- 5. ALTERAÇÕES NA TABELA CONTAS
-- =====================================================

-- Tornar nome obrigatório
ALTER TABLE contas ALTER COLUMN nome SET NOT NULL;

-- Adicionar constraint unique para conta_meta_trader
ALTER TABLE contas ADD CONSTRAINT contas_meta_trader_unique UNIQUE (conta_meta_trader);

-- Alterar tipos de dados para maior precisão
ALTER TABLE contas ALTER COLUMN margem_total TYPE NUMERIC(15,2);
ALTER TABLE contas ALTER COLUMN margem_disponivel TYPE NUMERIC(15,2);

-- Adicionar novos campos
ALTER TABLE contas ADD COLUMN margem_utilizada NUMERIC(15,2) DEFAULT 0.00;
ALTER TABLE contas ADD COLUMN ativa BOOLEAN DEFAULT TRUE NOT NULL;
ALTER TABLE contas ADD COLUMN status VARCHAR(20) DEFAULT 'ativa' NOT NULL;

-- Adicionar campos de auditoria
ALTER TABLE contas ADD COLUMN criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;
ALTER TABLE contas ADD COLUMN atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE contas ADD COLUMN criado_por INTEGER;
ALTER TABLE contas ADD COLUMN atualizado_por INTEGER;

-- Adicionar foreign keys de auditoria
ALTER TABLE contas ADD CONSTRAINT fk_contas_criado_por 
    FOREIGN KEY (criado_por) REFERENCES users(id);
ALTER TABLE contas ADD CONSTRAINT fk_contas_atualizado_por 
    FOREIGN KEY (atualizado_por) REFERENCES users(id);

-- =====================================================
-- 6. ALTERAÇÕES NA TABELA USERS
-- =====================================================

-- Adicionar constraint unique para CPF
ALTER TABLE users ADD CONSTRAINT users_cpf_unique UNIQUE (cpf);

-- Tornar tipo_de_user obrigatório
ALTER TABLE users ALTER COLUMN tipo_de_user SET NOT NULL;
ALTER TABLE users ALTER COLUMN tipo_de_user SET DEFAULT 'cliente';

-- Remover campo id_conta (BREAKING CHANGE)
ALTER TABLE users DROP COLUMN IF EXISTS id_conta;

-- Adicionar novos campos
ALTER TABLE users ADD COLUMN ativo BOOLEAN DEFAULT TRUE NOT NULL;
ALTER TABLE users ADD COLUMN email_verificado BOOLEAN DEFAULT FALSE NOT NULL;
ALTER TABLE users ADD COLUMN ultimo_login TIMESTAMP;

-- Adicionar campos de auditoria
ALTER TABLE users ADD COLUMN criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;
ALTER TABLE users ADD COLUMN atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE users ADD COLUMN criado_por INTEGER;
ALTER TABLE users ADD COLUMN atualizado_por INTEGER;

-- Adicionar foreign keys de auditoria (auto-referência)
ALTER TABLE users ADD CONSTRAINT fk_users_criado_por 
    FOREIGN KEY (criado_por) REFERENCES users(id);
ALTER TABLE users ADD CONSTRAINT fk_users_atualizado_por 
    FOREIGN KEY (atualizado_por) REFERENCES users(id);

-- Atualizar dados existentes
UPDATE users SET tipo_de_user = 'cliente' WHERE tipo_de_user IS NULL;

-- =====================================================
-- 7. ALTERAÇÕES NA TABELA ROBOS
-- =====================================================

-- Adicionar novos campos
ALTER TABLE robos ADD COLUMN ativo BOOLEAN DEFAULT TRUE NOT NULL;
ALTER TABLE robos ADD COLUMN versao VARCHAR;
ALTER TABLE robos ADD COLUMN tipo VARCHAR;

-- Adicionar campos de auditoria
ALTER TABLE robos ADD COLUMN criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;
ALTER TABLE robos ADD COLUMN atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE robos ADD COLUMN criado_por INTEGER;
ALTER TABLE robos ADD COLUMN atualizado_por INTEGER;

-- Adicionar foreign keys de auditoria
ALTER TABLE robos ADD CONSTRAINT fk_robos_criado_por 
    FOREIGN KEY (criado_por) REFERENCES users(id);
ALTER TABLE robos ADD CONSTRAINT fk_robos_atualizado_por 
    FOREIGN KEY (atualizado_por) REFERENCES users(id);

-- =====================================================
-- 8. CRIAÇÃO DE ÍNDICES PARA PERFORMANCE
-- =====================================================

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
CREATE INDEX idx_robos_do_user_id_user ON robos_do_user(id_user);
CREATE INDEX idx_robos_do_user_id_robo ON robos_do_user(id_robo);

-- Índices para consultas frequentes
CREATE INDEX idx_requisicoes_id_robo ON requisicoes(id_robo);
CREATE INDEX idx_ordens_id_user ON ordens(id_user);
CREATE INDEX idx_carteiras_id_user ON carteiras(id_user);

-- =====================================================
-- 9. TRIGGERS PARA ATUALIZAÇÃO AUTOMÁTICA DE TIMESTAMPS
-- =====================================================

-- Função para atualizar timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers para cada tabela
CREATE TRIGGER update_requisicoes_updated_at BEFORE UPDATE ON requisicoes 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_robos_do_user_updated_at BEFORE UPDATE ON robos_do_user 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ordens_updated_at BEFORE UPDATE ON ordens 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_contas_updated_at BEFORE UPDATE ON contas 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_robos_updated_at BEFORE UPDATE ON robos 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- 10. VERIFICAÇÕES FINAIS
-- =====================================================

-- Verificar se todas as requisições têm status de aprovação
DO $$
DECLARE
    count_null INTEGER;
BEGIN
    SELECT COUNT(*) INTO count_null FROM requisicoes WHERE aprovado IS NULL;
    IF count_null > 0 THEN
        RAISE EXCEPTION 'Existem % requisições sem status de aprovação', count_null;
    END IF;
    RAISE NOTICE 'Verificação de aprovação: OK';
END $$;

-- Verificar se todas as contas têm nome
DO $$
DECLARE
    count_null INTEGER;
BEGIN
    SELECT COUNT(*) INTO count_null FROM contas WHERE nome IS NULL OR nome = '';
    IF count_null > 0 THEN
        RAISE EXCEPTION 'Existem % contas sem nome', count_null;
    END IF;
    RAISE NOTICE 'Verificação de nomes de conta: OK';
END $$;

-- Verificar integridade referencial
DO $$
DECLARE
    count_orphan INTEGER;
BEGIN
    SELECT COUNT(*) INTO count_orphan 
    FROM ordens o 
    LEFT JOIN robos_do_user ru ON o.id_robo_user = ru.id 
    WHERE o.id_robo_user IS NOT NULL AND ru.id IS NULL;
    
    IF count_orphan > 0 THEN
        RAISE EXCEPTION 'Existem % ordens órfãs', count_orphan;
    END IF;
    RAISE NOTICE 'Verificação de integridade referencial: OK';
END $$;

-- =====================================================
-- COMMIT DA MIGRAÇÃO
-- =====================================================

-- Se chegou até aqui sem erros, commit das mudanças
COMMIT;

-- Mensagem de sucesso
SELECT 'MIGRAÇÃO PARA VERSÃO 5.0 CONCLUÍDA COM SUCESSO!' as status;

-- =====================================================
-- INSTRUÇÕES PÓS-MIGRAÇÃO
-- =====================================================

/*
PRÓXIMOS PASSOS APÓS EXECUTAR ESTE SCRIPT:

1. Reiniciar a aplicação com o código da versão 5.0
2. Verificar logs da aplicação para erros
3. Testar funcionalidades críticas:
   - Criação de requisições
   - Fluxo de aprovação
   - Cache Redis
   - Auditoria
4. Monitorar performance do banco de dados
5. Verificar se todos os relacionamentos estão funcionando

ROLLBACK (SE NECESSÁRIO):
Se algo der errado, restaure o backup:
psql -h localhost -U username -d database_name < backup_pre_v5.sql

SUPORTE:
Em caso de problemas, consulte o CHANGELOG_V5.md para detalhes
ou entre em contato com a equipe de desenvolvimento.
*/

