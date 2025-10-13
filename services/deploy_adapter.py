# -*- coding: utf-8 -*-
import os
import requests
from typing import Optional

# Motor GitHub que você já tinha
from services.deploy_pages_service import GitHubPagesDeployer


class RunnerDeployer:
    """Faz deploy via Runner local (/deploy/landing ou /deploy/landing/upload)."""
    def __init__(self):
        base = os.getenv("DEPLOY_RUNNER_BASE")
        token = os.getenv("DEPLOY_RUNNER_TOKEN")
        if not base or not token:
            raise RuntimeError("Defina DEPLOY_RUNNER_BASE e DEPLOY_RUNNER_TOKEN.")
        self.base = base.rstrip("/")
        self.token = token
        self._headers_json = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def dispatch(
        self,
        *,
        domain: str,
        slug: str,                # "", "dev", "beta/x", "x"
        zip_url: str,
        empresa: Optional[str] = None,
        id_empresa: Optional[int] = None,
        aplicacao_id: Optional[int] = None,
        api_base: Optional[str] = None,
    ) -> None:
        payload = {
            "commit": "",
            "api_token": "",
            "domain": domain,
            "slug": slug or "",
            "empresa": empresa or "",
            "zip_url": zip_url,
            "aplicacao_id": int(aplicacao_id or 0),
            "api_base": api_base or "",
            "cancel_in_progress": True,
        }
        url = f"{self.base}/deploy/landing"
        r = requests.post(url, json=payload, headers=self._headers_json, timeout=60)
        if r.status_code >= 300:
            raise RuntimeError(f"Runner deploy falhou ({r.status_code}): {r.text}")

    def dispatch_delete(self, *, domain: str, slug: str) -> None:
        # O runner atual NÃO expõe endpoint de delete.
        # Estratégia: por enquanto, só faz no-op e deixa o backend marcar 'desativado'.
        # (se/quando houver /delete no runner, basta implementar aqui)
        return


def get_deployer():
    target = (os.getenv("DEPLOY_TARGET") or "").strip().lower()
    if target == "runner":
        return RunnerDeployer()
    # fallback legado (GitHub)
    return GitHubPagesDeployer()
