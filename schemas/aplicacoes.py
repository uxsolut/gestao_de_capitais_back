# schemas/aplicacoes.py
# -*- coding: utf-8 -*-
from typing import Optional, Literal, List
from pydantic import BaseModel, Field

# ----------------- Tipos (compatíveis com os ENUMs do Postgres) -----------------
DominioEnum = Literal["pinacle.com.br", "gestordecapitais.com", "tetramusic.com.br"]
FrontBackEnum = Literal["frontend", "backend", "fullstack"]
EstadoEnum = Literal["producao", "beta", "dev", "desativado"]
ServidorEnum = Literal["teste 1", "teste 2"]

# ----------------- Base -----------------
class AplicacaoBase(BaseModel):
    # Todos opcionais para refletir NULL permitido no banco
    dominio: Optional[DominioEnum] = Field(
        None, description="Valor do enum global.dominio_enum"
    )

    # Quando None, pode representar homepage por domínio/estado
    slug: Optional[str] = Field(
        None,
        pattern=r"^[a-z0-9-]{1,64}$",
        description=(
            "Slug minúsculo com hífens (1 a 64 chars). "
            "Se omitido/None, a página pode ser a homepage do domínio/estado."
        ),
    )

    # BYTEA e URL agora opcionais
    url_completa: Optional[str] = Field(
        None, description="URL completa calculada no backend (opcional)."
    )

    front_ou_back: Optional[FrontBackEnum] = Field(
        None, description="Valor do enum gestor_capitais.frontbackenum"
    )
    estado: Optional[EstadoEnum] = Field(
        None, description="Valor do enum global.estado_enum"
    )

    id_empresa: Optional[int] = Field(
        None, description="FK opcional para global.empresas.id (ON DELETE SET NULL)."
    )

    # Booleana aceita NULL no banco; mantemos default False se vier ausente
    precisa_logar: Optional[bool] = Field(
        None, description="Se true, requer autenticação/JWT para acesso."
    )

    # ---------- Novos campos ----------
    anotacoes: Optional[str] = Field(None, description="Campo livre para anotações.")
    dados_de_entrada: Optional[List[str]] = Field(
        None, description="Lista de dados de entrada esperados (text[])."
    )
    tipos_de_retorno: Optional[List[str]] = Field(
        None, description="Lista de tipos de retorno/resultados (text[])."
    )
    rota: Optional[str] = Field(None, description="Rota (path) relativa para acesso.")
    porta: Optional[str] = Field(None, description="Porta do serviço (texto).")
    servidor: Optional[ServidorEnum] = Field(
        None, description="Enum global.servidor_enum."
    )

# ----------------- Create / Update -----------------
class AplicacaoCreate(AplicacaoBase):
    # bytes em Pydantic casa com BYTEA/LargeBinary no SQLAlchemy; agora opcional
    arquivo_zip: Optional[bytes] = Field(
        None, description="Arquivo ZIP (BYTEA) opcional."
    )

class AplicacaoUpdate(AplicacaoBase):
    # Para update, também opcional
    arquivo_zip: Optional[bytes] = Field(
        None, description="Arquivo ZIP (BYTEA) opcional para atualização."
    )

# ----------------- Response -----------------
class AplicacaoOut(AplicacaoBase):
    id: int

    class Config:
        from_attributes = True  # (Pydantic v2) substitui orm_mode=True
