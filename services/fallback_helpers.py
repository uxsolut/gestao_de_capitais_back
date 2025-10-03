# services/fallback_helpers.py
from typing import Optional, Iterable, Tuple
from sqlalchemy import text
from database import engine

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _norm_empresa_slug_for_sql(slug: str) -> str:
    """
    Mantém o slug recebido (ex.: 'gestao-de-capitais') para comparação.
    """
    return (slug or "").strip().lower()

def empresa_id_por_slug(empresa_slug: Optional[str]) -> Optional[int]:
    """
    Resolve empresa pelo 'slug' da URL (ex.: 'gestao-de-capitais').
    Tenta bater contra o nome da empresa (lower) 'slugificado' no SQL.
    """
    if not empresa_slug:
        return None

    slug = _norm_empresa_slug_for_sql(empresa_slug)

    # Normalização no Postgres: lower(nome) -> troca qualquer sequência não [a-z0-9]+ por '-'
    # Ex.: 'Gestão de Capitais S/A' -> 'gestao-de-capitais-s-a'
    sql = text("""
        SELECT id
        FROM global.empresas
        WHERE lower(
                regexp_replace(nome, '[^a-z0-9]+', '-', 'g')
              ) = :slug
        LIMIT 1
    """)
    with engine.begin() as conn:
        row = conn.execute(sql, {"slug": slug}).first()
        return int(row[0]) if row else None


def _find_url_aplicacao_por_desvio(
    dominio: str,
    empresa_id: Optional[int],
    estado: Optional[str],
    caso: str,  # valores do enum global.tipo_de_pagina_enum (ex.: 'login', 'nao_tem')
) -> Optional[str]:
    """
    Procura em global.aplicacoes, usando apenas essa tabela, na seguinte ordem:
      1) dominio + empresa_id + estado + desvio_caso
      2) dominio + empresa_id + NULL   + desvio_caso
      3) dominio + NULL       + estado + desvio_caso
      4) dominio + NULL       + NULL   + desvio_caso
    Retorna a url_completa da aplicação encontrada.
    """
    tries: Iterable[Tuple[Optional[int], Optional[str]]] = (
        (empresa_id, estado),
        (empresa_id, None),
        (None, estado),
        (None, None),
    )

    with engine.begin() as conn:
        for e_id, est in tries:
            row = conn.execute(
                text("""
                    SELECT a.url_completa
                      FROM global.aplicacoes a
                     WHERE a.dominio    = CAST(:dominio AS global.dominio_enum)
                       AND a.desvio_caso = CAST(:caso AS global.tipo_de_pagina_enum)
                       AND (a.id_empresa IS NOT DISTINCT FROM :empresa_id)
                       AND (a.estado     IS NOT DISTINCT FROM CAST(:estado AS global.estado_enum))
                  ORDER BY a.id DESC
                     LIMIT 1
                """),
                {
                    "dominio": dominio,
                    "empresa_id": e_id,
                    "estado": est,
                    "caso": caso,
                },
            ).first()
            if row and row[0]:
                return row[0]
    return None

# ---------------------------------------------------------
# Funções usadas pelo main/middleware
# ---------------------------------------------------------

def url_nao_tem(dominio: str, empresa_id: int, estado: Optional[str]) -> Optional[str]:
    """
    Destino quando o slug/rota não existe: usa aplicacoes.desvio_caso = 'nao_tem'.
    Busca na ordem de especificidade e retorna a url_completa.
    """
    return _find_url_aplicacao_por_desvio(
        dominio=dominio,
        empresa_id=empresa_id,
        estado=estado,
        caso="nao_tem",
    )

def url_login(dominio: str, empresa_id: int, estado: str) -> Optional[str]:
    """
    Destino de login quando precisa de autenticação: aplicacoes.desvio_caso = 'login'.
    Tenta (dominio, empresa_id, estado) e fallbacks como descrito.
    """
    return _find_url_aplicacao_por_desvio(
        dominio=dominio,
        empresa_id=empresa_id,
        estado=estado,
        caso="login",
    )

def precisa_logar(dominio: str, empresa_id: int, estado: str, slug: Optional[str]) -> Optional[bool]:
    """
    Verifica em global.aplicacoes se a rota precisa de login.
    Mantém a mesma consulta base que você já usava.
    """
    sql = text("""
        SELECT precisa_logar
          FROM global.aplicacoes
         WHERE dominio    = CAST(:dom AS global.dominio_enum)
           AND id_empresa = :empresa_id
           AND estado     = CAST(:estado AS global.estado_enum)
           AND slug IS NOT DISTINCT FROM :slug
         LIMIT 1
    """)
    with engine.begin() as conn:
        row = conn.execute(sql, {
            "dom": dominio,
            "empresa_id": empresa_id,
            "estado": estado,
            "slug": slug,
        }).first()
        return None if not row else (None if row[0] is None else bool(row[0]))
