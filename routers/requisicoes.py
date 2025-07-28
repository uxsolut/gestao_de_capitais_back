from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from models.requisicoes import Requisicao
from models.users import User
from schemas.requisicoes import (
    RequisicaoCreate, 
    RequisicaoUpdate,
    Requisicao as RequisicaoSchema, 
    RequisicaoDetalhada,
    RequisicaoCache
)
from auth.dependencies import get_db, get_current_user
from services.requisicao_service import RequisicaoService
from services.auditoria_service import AuditoriaService

router = APIRouter(prefix="/requisicoes", tags=["Requisicoes"])

# ---------- POST: Criar nova requisição ----------
@router.post("/", response_model=RequisicaoSchema, status_code=status.HTTP_201_CREATED)
def criar_requisicao(
    requisicao: RequisicaoCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cria uma nova requisição com fluxo de aprovação e cache integrado
    """
    try:
        # Verificar se usuário pode criar requisições
        if not current_user.pode_operar():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário não autorizado a criar requisições"
            )
        
        # Usar service para criar requisição
        requisicao_service = RequisicaoService(db)
        nova_requisicao = requisicao_service.criar_requisicao(
            requisicao.dict(), 
            current_user.id
        )
        
        # Registrar auditoria
        auditoria_service = AuditoriaService(db)
        auditoria_service.registrar_alteracao(
            tabela="requisicoes",
            registro_id=nova_requisicao.id,
            operacao="CREATE",
            dados_novos=requisicao.dict(),
            user_id=current_user.id,
            observacoes="Requisição criada via API"
        )
        
        return nova_requisicao
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno do servidor")

# ---------- GET: Listar requisições ----------
@router.get("/", response_model=List[RequisicaoDetalhada])
def listar_requisicoes(
    apenas_aprovadas: bool = Query(False, description="Filtrar apenas requisições aprovadas"),
    id_robo: Optional[int] = Query(None, description="Filtrar por ID do robô"),
    limit: int = Query(100, le=1000, description="Limite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginação"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista requisições com filtros opcionais
    """
    try:
        query = db.query(Requisicao)
        
        # Aplicar filtros
        if apenas_aprovadas:
            query = query.filter(Requisicao.aprovado == True)
        
        if id_robo:
            query = query.filter(Requisicao.id_robo == id_robo)
        
        # Se não for admin, mostrar apenas requisições do usuário
        if not current_user.is_admin:
            # Filtrar por requisições criadas pelo usuário ou de suas contas
            user_contas_ids = [conta.id for conta in current_user.get_contas_ativas()]
            query = query.filter(
                (Requisicao.criado_por == current_user.id) |
                (Requisicao.ids_contas.overlap(user_contas_ids))
            )
        
        # Aplicar paginação
        requisicoes = query.offset(offset).limit(limit).all()
        
        # Registrar acesso a dados sensíveis
        auditoria_service = AuditoriaService(db)
        auditoria_service.registrar_acesso_dados_sensíveis(
            user_id=current_user.id,
            recurso="requisicoes",
            dados_acessados=f"Lista de {len(requisicoes)} requisições"
        )
        
        return requisicoes
        
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno do servidor")

# ---------- GET: Obter requisição específica ----------
@router.get("/{requisicao_id}", response_model=RequisicaoDetalhada)
def obter_requisicao(
    requisicao_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Obtém uma requisição específica por ID
    """
    requisicao = db.query(Requisicao).filter(Requisicao.id == requisicao_id).first()
    
    if not requisicao:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisição não encontrada")
    
    # Verificar permissão de acesso
    if not current_user.is_admin and requisicao.criado_por != current_user.id:
        user_contas_ids = [conta.id for conta in current_user.get_contas_ativas()]
        if not any(conta_id in user_contas_ids for conta_id in (requisicao.ids_contas or [])):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    
    # Registrar acesso
    auditoria_service = AuditoriaService(db)
    auditoria_service.registrar_acesso_dados_sensíveis(
        user_id=current_user.id,
        recurso="requisicoes",
        dados_acessados=f"Requisição ID {requisicao_id}"
    )
    
    return requisicao

# ---------- PUT: Atualizar requisição ----------
@router.put("/{requisicao_id}", response_model=RequisicaoSchema)
def atualizar_requisicao(
    requisicao_id: int,
    requisicao_update: RequisicaoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Atualiza uma requisição existente
    """
    requisicao = db.query(Requisicao).filter(Requisicao.id == requisicao_id).first()
    
    if not requisicao:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisição não encontrada")
    
    # Verificar permissão
    if not current_user.is_admin and requisicao.criado_por != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    
    # Salvar dados anteriores para auditoria
    dados_anteriores = {
        "comentario_ordem": requisicao.comentario_ordem,
        "symbol": requisicao.symbol,
        "quantidade": float(requisicao.quantidade) if requisicao.quantidade else None,
        "preco": float(requisicao.preco) if requisicao.preco else None,
        "aprovado": requisicao.aprovado
    }
    
    # Atualizar campos
    update_data = requisicao_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(requisicao, field, value)
    
    requisicao.atualizado_por = current_user.id
    
    try:
        db.commit()
        db.refresh(requisicao)
        
        # Se aprovação foi alterada, invalidar cache
        if 'aprovado' in update_data:
            requisicao_service = RequisicaoService(db)
            requisicao_service.invalidar_cache_requisicao(requisicao_id)
        
        # Registrar auditoria
        auditoria_service = AuditoriaService(db)
        auditoria_service.registrar_alteracao(
            tabela="requisicoes",
            registro_id=requisicao_id,
            operacao="UPDATE",
            dados_anteriores=dados_anteriores,
            dados_novos=update_data,
            user_id=current_user.id
        )
        
        return requisicao
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao atualizar requisição")

# ---------- GET: Obter requisição do cache ----------
@router.get("/{requisicao_id}/cache", response_model=Optional[RequisicaoCache])
def obter_requisicao_cache(
    requisicao_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Obtém requisição do cache Redis (apenas se aprovada)
    """
    try:
        requisicao_service = RequisicaoService(db)
        dados_cache = requisicao_service.obter_requisicao_do_cache(requisicao_id)
        
        if not dados_cache:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Requisição não encontrada no cache ou não aprovada"
            )
        
        return dados_cache
        
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao acessar cache")

# ---------- GET: Listar apenas aprovadas (para consumo) ----------
@router.get("/aprovadas/", response_model=List[RequisicaoSchema])
def listar_requisicoes_aprovadas(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista apenas requisições aprovadas (prontas para consumo)
    """
    try:
        requisicao_service = RequisicaoService(db)
        requisicoes = requisicao_service.listar_requisicoes_aprovadas()
        
        # Filtrar por permissões se não for admin
        if not current_user.is_admin:
            user_contas_ids = [conta.id for conta in current_user.get_contas_ativas()]
            requisicoes = [
                req for req in requisicoes 
                if req.criado_por == current_user.id or 
                any(conta_id in user_contas_ids for conta_id in (req.ids_contas or []))
            ]
        
        return requisicoes
        
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno do servidor")

