from datetime import date
from typing import List, Optional, Iterable, Dict, Tuple

import structlog
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func, select, text, and_
from sqlalchemy.orm import Session

from auth.dependencies import get_db, get_current_user
from schemas.dashboard import (
    DashboardResponse,
    DashboardMetricas,
    DashboardResumoDados,
    MargemPaisResponse,
    MargemPaisItem,
    # novos (gráfico)
    TipoMercadoOut,
    AtivoOut,
    PontoSerie,
    SerieAtivo,
    SeriesResponse,
)
from models.users import User
from models.carteiras import Carteira
from models.robos_do_user import RoboDoUser
from models.ordens import Ordem
from models.contas import Conta
from models.corretoras import Corretora

# >>> models necessários para o gráfico
from models.ativos import Ativo            # id, descricao, symbol, pais, criado_em
from models.relatorios import Relatorio    # id, resultado_do_dia, id_user, data_cotacao, id_ativo, tipo_mercado

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
logger = structlog.get_logger()


# ==============================================================================
# EXISTENTES
# ==============================================================================

@router.get("/", response_model=DashboardResponse)
def get_dashboard_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    carteiras = db.query(Carteira).filter(Carteira.id_user == current_user.id).all()
    robos = db.query(RoboDoUser).filter(RoboDoUser.id_user == current_user.id).all()
    ordens = db.query(Ordem).filter(Ordem.id_user == current_user.id).all()

    metricas = DashboardMetricas(
        total_carteiras=len(carteiras),
        total_robos=len(robos),
        total_ordens=len(ordens)
    )

    resumo = DashboardResumoDados(
        carteiras_recentes=[c.nome for c in carteiras[-5:]],
        ordens_recentes=[f"{o.tipo} ({o.conta_meta_trader})" for o in ordens[-5:]]
    )

    return DashboardResponse(metricas=metricas, resumo=resumo)


@router.get("/margem-por-pais", response_model=MargemPaisResponse)
def margem_por_pais(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Soma a margem_total das CONTAS do usuário autenticado,
    agrupando pelo país da CORRETORA (campo pais_enum).
    - Só inclui países com total > 0
    """
    rows = (
        db.query(
            Corretora.pais.label("pais"),
            func.coalesce(func.sum(Conta.margem_total), 0).label("total"),
        )
        .join(Conta, Conta.id_corretora == Corretora.id)
        .join(Carteira, Carteira.id == Conta.id_carteira)
        .filter(Carteira.id_user == current_user.id)
        .group_by(Corretora.pais)
        .all()
    )

    itens_dyn: List[MargemPaisItem] = []
    total_geral = 0.0

    for pais_val, soma in rows:
        pais = getattr(pais_val, "value", pais_val)
        pais = str(pais)
        valor = float(soma or 0)
        if valor <= 0:
            continue

        itens_dyn.append(MargemPaisItem(pais=pais, margem_total=round(valor, 2)))
        total_geral += valor

    itens_dyn.sort(key=lambda x: x.margem_total, reverse=True)

    return MargemPaisResponse(total=round(total_geral, 2), itens=itens_dyn)


# ==============================================================================
# NOVOS: ENDPOINTS DO GRÁFICO DE EVOLUÇÃO DOS ATIVOS
# ==============================================================================

@router.get("/grafico/tipos-mercado", response_model=List[TipoMercadoOut],
            summary="Lista os valores do enum public.tipo_de_mercado")
def listar_tipos_mercado(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[TipoMercadoOut]:
    """
    Lê os valores do enum diretamente do PostgreSQL.
    """
    rows = db.execute(
        text("SELECT unnest(enum_range(NULL::public.tipo_de_mercado))::text AS v")
    ).all()
    return [TipoMercadoOut(value=v, label=v) for (v,) in rows]


@router.get("/grafico/ativos", response_model=List[AtivoOut],
            summary="Lista de ativos com filtro por tipo_mercado (quando informado)")
def listar_ativos(
    tipos: Optional[List[str]] = Query(
        None, description="Filtrar por tipo_mercado (ex.: Moeda, Indice, Robo). Pode repetir o parâmetro."
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[AtivoOut]:
    """
    Retorna ativos que possuem pelo menos um relatório do usuário logado,
    opcionalmente filtrando pelos tipos informados.
    """
    q = (
        select(Ativo)
        .join(Relatorio, Relatorio.id_ativo == Ativo.id)
        .where(Relatorio.id_user == current_user.id)
    )

    if tipos:
        tipos_norm = [t.strip() for t in tipos if t and t.strip()]
        if tipos_norm:
            q = q.where(Relatorio.tipo_mercado.in_(tipos_norm))

    q = q.group_by(Ativo.id).order_by(Ativo.descricao.asc())
    ativos = db.execute(q).scalars().all()
    return [AtivoOut.model_validate(a) for a in ativos]


def _group_expr(group_by: Optional[str]):
    """
    Ajuda para agrupar por dia/semana/mês com date_trunc.
    """
    gb = (group_by or "day").lower()
    if gb not in {"day", "week", "month"}:
        gb = "day"
    return gb, func.date_trunc(gb, Relatorio.data_cotacao).label("bucket")


@router.get("/grafico/series", response_model=SeriesResponse,
            summary="Séries de evolução por ativo (data_cotacao x resultado_do_dia)")
def series_por_ativo(
    ativo_ids: List[int] = Query(..., description="IDs dos ativos a plotar. Pode repetir o parâmetro."),
    tipos: Optional[List[str]] = Query(None, description="Filtrar pelos valores do enum tipo_mercado"),
    start: Optional[date] = Query(None, description="Data inicial (YYYY-MM-DD)"),
    end: Optional[date] = Query(None, description="Data final (YYYY-MM-DD)"),
    group_by: Optional[str] = Query("day", description="Agrupar por 'day' | 'week' | 'month'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SeriesResponse:
    """
    Retorna séries por ativo. Por padrão, agrega por 'day' (date_trunc).
    - Filtra por usuário (Relatorio.id_user == current_user.id)
    - Filtros opcionais: tipos, start, end
    - Se houver múltiplos relatórios no mesmo bucket, usa AVG(resultado_do_dia)
    """
    if not ativo_ids:
        raise HTTPException(status_code=400, detail="Informe pelo menos um ativo em 'ativo_ids'.")

    gb_key, gb_expr = _group_expr(group_by)

    where_clauses = [Relatorio.id_ativo.in_(ativo_ids), Relatorio.id_user == current_user.id]
    if tipos:
        tipos_norm = [t.strip() for t in tipos if t and t.strip()]
        if tipos_norm:
            where_clauses.append(Relatorio.tipo_mercado.in_(tipos_norm))
    if start:
        where_clauses.append(Relatorio.data_cotacao >= start)
    if end:
        where_clauses.append(Relatorio.data_cotacao <= end)

    q = (
        select(
            Relatorio.id_ativo.label("ativo_id"),
            gb_expr,
            func.avg(Relatorio.resultado_do_dia).label("valor"),
        )
        .where(and_(*where_clauses))
        .group_by(Relatorio.id_ativo, gb_expr)
        .order_by(Relatorio.id_ativo.asc(), gb_expr.asc())
    )

    rows: Iterable[Tuple[int, date, float]] = db.execute(q).all()

    # Metadados dos ativos
    ativos_map: Dict[int, Tuple[str, str]] = {
        a.id: (a.symbol or "", a.descricao or "")
        for a in db.execute(select(Ativo).where(Ativo.id.in_(ativo_ids))).scalars().all()
    }

    # Monta resposta agrupando pontos por ativo
    series_dict: Dict[int, List[PontoSerie]] = {}
    for ativo_id, bucket_dt, valor in rows:
        if bucket_dt is None or valor is None:
            continue
        series_dict.setdefault(ativo_id, []).append(
            PontoSerie(data=bucket_dt.date().isoformat(), valor=float(valor))
        )

    series_out: List[SerieAtivo] = []
    for aid in ativo_ids:
        symbol, desc = ativos_map.get(aid, ("", ""))
        pontos = series_dict.get(aid, [])
        series_out.append(SerieAtivo(
            ativo_id=aid,
            symbol=symbol,
            descricao=desc,
            pontos=pontos
        ))

    return SeriesResponse(series=series_out)
