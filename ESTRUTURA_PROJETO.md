# Estrutura Completa do Projeto v5.0

## 📁 Visão Geral

Este projeto contém uma aplicação completa de gestão de capitais com:
- **Backend**: FastAPI (Python) - API REST robusta
- **Frontend**: Flutter (Dart) - Interface moderna e responsiva

## 🏗️ Estrutura de Diretórios

```
projeto_v5/
├── 📁 Backend (FastAPI)
│   ├── auth/                    # Autenticação e autorização
│   ├── middleware/              # Middlewares customizados
│   ├── models/                  # Modelos de dados (SQLAlchemy)
│   ├── routers/                 # Endpoints da API
│   ├── schemas/                 # Esquemas de validação (Pydantic)
│   ├── services/                # Lógica de negócio
│   ├── tests/                   # Testes automatizados
│   ├── main.py                  # Arquivo principal da API
│   ├── config.py                # Configurações
│   ├── database.py              # Configuração do banco
│   └── requirements.txt         # Dependências Python
│
├── 📁 Frontend (Flutter)
│   ├── dashboard_app/
│   │   ├── lib/
│   │   │   ├── config/          # Configurações do app
│   │   │   ├── controllers/     # Gerenciamento de estado
│   │   │   ├── models/          # Modelos de dados Dart
│   │   │   ├── pages/           # Telas da aplicação
│   │   │   ├── services/        # Serviços de API
│   │   │   ├── widgets/         # Componentes reutilizáveis
│   │   │   └── main.dart        # Arquivo principal Flutter
│   │   ├── web/                 # Assets para web
│   │   ├── test/                # Testes Flutter
│   │   ├── pubspec.yaml         # Dependências Flutter
│   │   └── README.md            # Documentação Flutter
│
└── 📁 Documentação
    ├── CHANGELOG_V5.md          # Mudanças da versão 5.0
    ├── README_V5.md             # Guia completo
    ├── MIGRATION_SCRIPT.sql     # Script de migração
    ├── MELHORIAS_V2.md          # Melhorias da v2.0
    └── ESTRUTURA_PROJETO.md     # Este arquivo
```

## 🔧 Backend (FastAPI)

### Principais Componentes:

**Models (SQLAlchemy):**
- `users.py` - Usuários do sistema
- `requisicoes.py` - Requisições de trading (⭐ com fluxo de aprovação)
- `ordens.py` - Ordens de compra/venda
- `contas.py` - Contas de trading
- `robos.py` - Robôs de trading
- `carteiras.py` - Carteiras de investimento

**Services (Lógica de Negócio):**
- `requisicao_service.py` - Gerencia fluxo completo de requisições + cache Redis
- `auditoria_service.py` - Sistema de auditoria e compliance
- `cache_service.py` - Gerenciamento de cache Redis

**Routers (API Endpoints):**
- `/users/` - Gestão de usuários e autenticação
- `/requisicoes/` - Gestão de requisições (⭐ com auditoria)
- `/ordens/` - Gestão de ordens
- `/contas/` - Gestão de contas
- `/robos/` - Gestão de robôs

### Tecnologias Backend:
- FastAPI (Framework web)
- SQLAlchemy (ORM)
- Pydantic (Validação)
- PostgreSQL (Banco de dados)
- Redis (Cache)
- JWT (Autenticação)

## 📱 Frontend (Flutter)

### Principais Componentes:

**Pages (Telas):**
- `home_page.dart` - Tela inicial
- `login_page.dart` - Autenticação
- `main_app.dart` - App principal
- `relatorios_page.dart` - Relatórios avançados
- `admin/` - Telas administrativas
- `cliente/` - Telas do cliente

**Widgets (Componentes):**
- `control_center.dart` - Central de controle analógica (⭐ design high-tech)
- `date_range_filter.dart` - Filtros de data
- `benchmark_selector.dart` - Seletor de benchmarks
- `common/` - Componentes reutilizáveis

**Controllers (Estado):**
- `navegacao_controller.dart` - Navegação
- `dashboard_controller.dart` - Dashboard
- `login_controller.dart` - Autenticação
- `home_controller.dart` - Tela inicial

### Tecnologias Frontend:
- Flutter (Framework UI)
- Provider (Gerenciamento de estado)
- fl_chart (Gráficos)
- HTTP (Comunicação com API)
- Shared Preferences (Armazenamento local)

## 🔄 Integração Backend-Frontend

### Fluxo de Dados:
1. **Flutter** faz requisições HTTP para **FastAPI**
2. **FastAPI** processa via **Services** e **Models**
3. **Redis** armazena cache de requisições aprovadas
4. **PostgreSQL** persiste dados principais
5. **Auditoria** registra todas as operações

### Autenticação:
- JWT tokens gerados pelo backend
- Armazenados no Flutter via Secure Storage
- Validação automática em todas as requisições

## 🚀 Como Executar

### Backend:
```bash
cd projeto_v5/
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend:
```bash
cd projeto_v5/dashboard_app/
flutter pub get
flutter run -d web
```

## 📊 Funcionalidades Principais

### ⭐ Fluxo de Aprovação de Requisições (v5.0):
1. Requisição criada com `aprovado = false`
2. Cache processado no Redis
3. Após cache completo: `aprovado = true`
4. Requisição disponível para consumo

### 🎨 Interface High-Tech:
- Central de controle analógica
- Gráficos comparativos animados
- Design dark profissional
- Relatórios avançados com benchmarks

### 🔒 Segurança e Auditoria:
- Todas as operações auditadas
- Logs estruturados
- Controle de permissões granular
- Compliance financeiro

## 📈 Melhorias da v5.0

- ✅ Campo `aprovado` em requisições
- ✅ Sistema de auditoria completo
- ✅ Services especializados
- ✅ Relacionamentos corrigidos
- ✅ Cache Redis integrado
- ✅ Validações rigorosas
- ✅ Documentação completa

---

**Versão:** 5.0 Completa (Backend + Frontend)  
**Tamanho:** ~12MB  
**Arquivos:** 200+ arquivos incluídos

