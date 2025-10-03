# services/fallback_helpers.py
from typing import Optional
from sqlalchemy import text
from database import engine

def empresa_id_por_slug(empresa_slug: Optional[str]) -> Optional[int]:
    if not empresa_slug:
        return None
    sql = text("""
        SELECT id FROM global.empresas
        WHERE lower(nome) = :slug
        LIMIT 1
    """)
    with engine.begin() as conn:
        row = conn.execute(sql, {"slug": empresa_slug}).first()
        return int(row[0]) if row else None

def url_nao_tem(dominio: str, empresa_id: int, estado: Optional[str]) -> Optional[str]:
    sql = text("""
        SELECT a.url_completa
        FROM global.desvio_rota_front d
        JOIN global.aplicacoes a ON a.id = d.id_aplicacao
        WHERE d.tipo_de_pagina = 'nao_tem'
          AND a.dominio    = CAST(:dom AS global.dominio_enum)
          AND a.id_empresa = :empresa_id
        ORDER BY
          CASE
            WHEN :estado IS NULL THEN 0
            WHEN a.estado = CAST(:estado AS global.estado_enum) THEN 1
            ELSE 0
          END DESC,
          a.id DESC
        LIMIT 1
    """)
    with engine.begin() as conn:
        row = conn.execute(sql, {"dom": dominio, "empresa_id": empresa_id, "estado": estado}).first()
        return row[0] if row else None

def url_login(dominio: str, empresa_id: int, estado: str) -> Optional[str]:
    sql = text("""
        SELECT a.url_completa
        FROM global.desvio_rota_front d
        JOIN global.aplicacoes a ON a.id = d.id_aplicacao
        WHERE d.tipo_de_pagina = 'login'
          AND a.dominio    = CAST(:dom AS global.dominio_enum)
          AND a.id_empresa = :empresa_id
          AND a.estado     = CAST(:estado AS global.estado_enum)
        ORDER BY a.id DESC
        LIMIT 1
    """)
    with engine.begin() as conn:
        row = conn.execute(sql, {"dom": dominio, "empresa_id": empresa_id, "estado": estado}).first()
        return row[0] if row else None

def precisa_logar(dominio: str, empresa_id: int, estado: str, slug: Optional[str]) -> Optional[bool]:
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
            "dom": dominio, "empresa_id": empresa_id, "estado": estado, "slug": slug
        }).first()
        return None if not row else (None if row[0] is None else bool(row[0]))
