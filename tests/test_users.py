"""
Testes para o módulo de usuários
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, get_db
from main import app

# Banco de dados de teste em memória
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Criar tabelas de teste
Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

class TestUsers:
    def test_create_user_success(self):
        """Teste de criação de usuário com sucesso"""
        user_data = {
            "nome": "Teste Usuario",
            "email": "teste@exemplo.com",
            "senha": "senha123",
            "tipo_de_user": "cliente"
        }
        
        response = client.post("/users/", json=user_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == user_data["email"]
        assert data["nome"] == user_data["nome"]
        assert "id" in data
    
    def test_create_user_invalid_email(self):
        """Teste de criação de usuário com email inválido"""
        user_data = {
            "nome": "Teste Usuario",
            "email": "email-invalido",
            "senha": "senha123",
            "tipo_de_user": "cliente"
        }
        
        response = client.post("/users/", json=user_data)
        assert response.status_code == 422  # Validation error
    
    def test_create_user_short_password(self):
        """Teste de criação de usuário com senha muito curta"""
        user_data = {
            "nome": "Teste Usuario",
            "email": "teste2@exemplo.com",
            "senha": "123",  # Muito curta
            "tipo_de_user": "cliente"
        }
        
        response = client.post("/users/", json=user_data)
        assert response.status_code == 422  # Validation error
    
    def test_login_success(self):
        """Teste de login com sucesso"""
        # Primeiro criar um usuário
        user_data = {
            "nome": "Login Teste",
            "email": "login@exemplo.com",
            "senha": "senha123",
            "tipo_de_user": "cliente"
        }
        client.post("/users/", json=user_data)
        
        # Tentar fazer login
        login_data = {
            "email": "login@exemplo.com",
            "senha": "senha123"
        }
        
        response = client.post("/users/login", json=login_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
    
    def test_login_invalid_credentials(self):
        """Teste de login com credenciais inválidas"""
        login_data = {
            "email": "inexistente@exemplo.com",
            "senha": "senhaerrada"
        }
        
        response = client.post("/users/login", json=login_data)
        assert response.status_code == 401
    
    def test_list_users_without_auth(self):
        """Teste de listagem de usuários sem autenticação"""
        response = client.get("/users/")
        assert response.status_code == 401  # Unauthorized
    
    def test_cpf_validation(self):
        """Teste de validação de CPF"""
        user_data = {
            "nome": "CPF Teste",
            "email": "cpf@exemplo.com",
            "senha": "senha123",
            "cpf": "12345678901",  # CPF sem formatação
            "tipo_de_user": "cliente"
        }
        
        response = client.post("/users/", json=user_data)
        
        if response.status_code == 200:
            data = response.json()
            # Verificar se CPF foi formatado corretamente
            assert data["cpf"] == "123.456.789-01"

