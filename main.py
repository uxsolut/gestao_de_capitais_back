from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from database import engine, Base
from prometheus_fastapi_instrumentator import Instrumentator
from config import settings
from middleware.error_handler import ErrorHandlerMiddleware

from models import corretoras  
from routers import robos, users, robos_do_user, requisicoes, carteiras, ordens, contas, corretoras, aplicacao, versao_aplicacao, projeto

# Criação das tabelas no banco
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Meta Trade API",
    version="2.0.0",
    description="API de Gestão de Capitais com melhorias de segurança",
    debug=settings.DEBUG
)

# Middleware de tratamento de erros
app.add_middleware(ErrorHandlerMiddleware)

# CORS com configuração segura
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Rotas
@app.get("/")
def read_root():
    return {"mensagem": "API online com sucesso!"}

app.include_router(ordens.router)
app.include_router(robos.router)
app.include_router(users.router)          
app.include_router(robos_do_user.router)  
app.include_router(requisicoes.router)
app.include_router(carteiras.router)
app.include_router(contas.router)
app.include_router(corretoras.router)
app.include_router(aplicacao.router)
app.include_router(versao_aplicacao.router)
app.include_router(projeto.router)

# OpenAPI customizado
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Meta Trade API",
        version="1.0.0",
        description="Documentação da API da Meta Trade com autenticação JWT",
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    openapi_schema["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# ✅ Expor métricas no /metrics (ANTES de rodar)
Instrumentator().instrument(app).expose(app)

# Execução local
import os
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
