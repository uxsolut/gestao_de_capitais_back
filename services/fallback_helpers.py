# services/fallback_helpers.py
# -*- coding: utf-8 -*-
from typing import Optional, Iterable, Tuple, List
from sqlalchemy import text
from database import engine

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

_DEVLIKE = {"dev", "beta"}

def _norm_empresa_slug_for_sql(slug: Optional[str]) -> str:
    """
    Mantém o slug recebido (ex.: 'gestao-de-capitais') para comparação direta.
    """
    return (slug or "").strip().lower()

def _estado_normalizado(estado: Optional[str]) -> str:
    """
    Normaliza o estado vindo da URL para ('dev'|'beta'|'producao').
    Qualquer outro valor cai em 'producao'.
    """
    if not estado:
        return "producao"
    e = estado.strip().lower()
    return e if e in _DEVLIKE or e == "producao" else "producao"

def _fallback_estados(estado: Optional[str]) -> List[str]:
    """
    Ordem de fallback:
      - se estado for 'dev' ou 'beta' -> ['dev|beta', 'producao']
      - se 'producao'                 -> ['producao'] apenas
    """
    e = _estado_normalizado(estado)
    return [e, "producao"] if e in _DEVLIKE else ["producao"]

def empresa_id_por_slug(empresa_slug: Optional[str]) -> Optional[int]:
    """
    Resolve empresa pelo 'slug' da URL (ex.: 'gestao-de-capitais').
    **Usa a coluna slug da tabela global.empresas** (mais correto que derivar de nome).
    """
    if not empresa_slug:
        return None

    slug = _norm_empresa_slug_for_sql(empresa_slug)

    sql = text("""
        SELECT id
          FROM global.empresas
         WHERE slug = :slug
         LIMIT 1
    """)
    with engine.begin() as conn:
        row = conn.execute(sql, {"slug": slug}).first()
        return int(row[0]) if row else None


def _find_url_aplicacao_por_desvio(
    dominio: str,
    empresa_id: Optional[int],
    estado: Optional[str],
    caso: str,  # valores do enum global.tipo_de_pagina_enum ('login' | 'nao_tem' | ...)
) -> Optional[str]:
    """
    Procura em global.aplicacoes obedecendo:
      - Tenta (dominio, empresa_id, estado)
      - Se não achar e estado != 'producao', tenta (dominio, empresa_id, 'producao')
      - Se ainda não achar, repete os dois passos acima com empresa_id = NULL (barreira por empresa cai)
    """
    estados = _fallback_estados(estado)

    with engine.begin() as conn:
        # 1) Com empresa_id (se houver)
        if empresa_id is not None:
            for est in estados:
                row = conn.execute(
                    text("""
                        SELECT a.url_completa
                          FROM global.aplicacoes a
                         WHERE a.dominio::text = :dominio
                           AND a.desvio_caso = CAST(:caso AS global.tipo_de_pagina_enum)
                           AND a.id_empresa  = :empresa_id
                           AND a.estado      = CAST(:estado AS global.estado_enum)
                         ORDER BY a.id DESC
                         LIMIT 1
                    """),
                    {"dominio": dominio, "empresa_id": empresa_id, "estado": est, "caso": caso},
                ).first()
                if row and row[0]:
                    return row[0]

        # 2) Sem empresa_id (barreira cai)
        for est in estados:
            row = conn.execute(
                text("""
                    SELECT a.url_completa
                      FROM global.aplicacoes a
                     WHERE a.dominio::text = :dominio
                       AND a.desvio_caso = CAST(:caso AS global.tipo_de_pagina_enum)
                       AND a.id_empresa IS NULL
                       AND a.estado      = CAST(:estado AS global.estado_enum)
                     ORDER BY a.id DESC
                     LIMIT 1
                """),
                {"dominio": dominio, "estado": est, "caso": caso},
            ).first()
            if row and row[0]:
                return row[0]

    return None

# ---------------------------------------------------------
# Funções usadas pelo main/middleware
# ---------------------------------------------------------

def url_nao_tem(dominio: str, empresa_id: Optional[int], estado: Optional[str]) -> Optional[str]:
    """
    Destino quando o slug/rota não existe: usa aplicacoes.desvio_caso = 'nao_tem'.
    Faz fallback do estado (dev/beta -> producao).
    Aceita empresa_id None (cai barreira por empresa).
    """
    return _find_url_aplicacao_por_desvio(
        dominio=dominio,
        empresa_id=empresa_id,
        estado=estado,
        caso="nao_tem",
    )

def url_login(dominio: str, empresa_id: Optional[int], estado: Optional[str]) -> Optional[str]:
    """
    Destino de login quando precisa de autenticação: aplicacoes.desvio_caso = 'login'.
    Mesmo fallback de estado e empresa.
    """
    return _find_url_aplicacao_por_desvio(
        dominio=dominio,
        empresa_id=empresa_id,
        estado=estado,
        caso="login",
    )

def precisa_logar(
    dominio: str,
    empresa_id: Optional[int],
    estado: Optional[str],
    slug: Optional[str],
) -> Optional[bool]:
    """
    Verifica em global.aplicacoes se a rota (dominio, empresa, estado, slug) precisa de login.
    Aplica fallback de estado: tenta estado pedido; se não achar e for dev/beta, tenta producao.
    Retorna:
      - True/False se achou um registro com 'precisa_logar' definido;
      - None se não achou nenhum registro correspondente.
    """
    estados = _fallback_estados(estado)

    with engine.begin() as conn:
        # Com empresa_id (se houver)
        if empresa_id is not None:
            for est in estados:
                row = conn.execute(
                    text("""
                        SELECT a.precisa_logar
                          FROM global.aplicacoes a
                         WHERE a.dominio::text = :dominio
                           AND a.id_empresa = :empresa_id
                           AND a.estado = CAST(:estado AS global.estado_enum)
                           AND a.slug  IS NOT DISTINCT FROM :slug
                         ORDER BY a.id DESC
                         LIMIT 1
                    """),
                    {"dominio": dominio, "empresa_id": empresa_id, "estado": est, "slug": slug},
                ).first()
                if row is not None:
                    return None if row[0] is None else bool(row[0])

        # Sem empresa_id
        for est in estados:
            row = conn.execute(
                text("""
                    SELECT a.precisa_logar
                      FROM global.aplicacoes a
                     WHERE a.dominio::text = :dominio
                       AND a.id_empresa IS NULL
                       AND a.estado = CAST(:estado AS global.estado_enum)
                       AND a.slug  IS NOT DISTINCT FROM :slug
                     ORDER BY a.id DESC
                     LIMIT 1
                """),
                {"dominio": dominio, "estado": est, "slug": slug},
            ).first()
            if row is not None:
                return None if row[0] is None else bool(row[0])

    return None
