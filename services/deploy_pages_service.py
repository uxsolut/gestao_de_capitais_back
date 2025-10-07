# services/deploy_pages_service.py
# -*- coding: utf-8 -*-
import os
import requests
from typing import Optional

class GitHubPagesDeployer:
    def __init__(self):
        self.owner = os.getenv("GITHUB_OWNER")
        self.repo = os.getenv("GITHUB_REPO")
        self.ref = os.getenv("GITHUB_REF", "main")
        # nome do arquivo do workflow (ex.: ".github/workflows/deploy-landing.yml" ou "deploy-landing.yml")
        self.workflow_file = os.getenv("WORKFLOW_FILE", "deploy-landing.yml")
        self.token = os.getenv("GITHUB_TOKEN_PAGES")
        self.delete_workflow_file = os.getenv("DELETE_WORKFLOW_FILE", "delete-landing.yml")
        self.delete_event = os.getenv("DELETE_EVENT", "delete-landing")

        if not all([self.owner, self.repo, self.workflow_file, self.token]):
            raise RuntimeError("Defina GITHUB_OWNER, GITHUB_REPO, WORKFLOW_FILE e GITHUB_TOKEN_PAGES.")

        self._headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }

    def dispatch(
        self,
        *,
        domain: str,
        slug: str,                    # "", "dev", "beta/x", "x" (SEM empresa)
        zip_url: str,
        empresa: Optional[str] = None,   # nome já minúsculo
        id_empresa: Optional[int] = None,
        aplicacao_id: Optional[int] = None,   # <<< NOVO (obrigatório pro workflow atual)
        api_base: Optional[str] = None        # opcional (workflow tem default)
    ) -> None:
        """
        Dispara o workflow de deploy com os inputs esperados.
        """
        url = (
            f"https://api.github.com/repos/{self.owner}/{self.repo}"
            f"/actions/workflows/{self.workflow_file}/dispatches"
        )

        inputs = {
            "domain": domain,
            "slug": slug,
            "zip_url": zip_url,
        }
        if empresa:
            inputs["empresa"] = empresa
        if id_empresa is not None:
            inputs["id_empresa"] = str(id_empresa)
        if aplicacao_id is not None:              # <<< envia para o workflow
            inputs["aplicacao_id"] = str(aplicacao_id)
        if api_base:                               # <<< opcional; workflow tem default
            inputs["api_base"] = api_base

        r = requests.post(
            url,
            json={"ref": self.ref, "inputs": inputs},
            headers=self._headers,
            timeout=30,
        )
        if r.status_code not in (201, 204):
            raise RuntimeError(f"Falha ao disparar workflow ({r.status_code}): {r.text}")

    def dispatch_delete(self, *, domain: str, slug: str) -> None:
        """
        Tenta primeiro via repository_dispatch (event customizado),
        se não, cai para workflow_dispatch do arquivo de delete.
        """
        url_repo = f"https://api.github.com/repos/{self.owner}/{self.repo}/dispatches"
        r = requests.post(
            url_repo,
            json={"event_type": self.delete_event, "client_payload": {"domain": domain, "slug": slug}},
            headers=self._headers,
            timeout=30,
        )
        if r.status_code == 204:
            return

        url_wf = (
            f"https://api.github.com/repos/{self.owner}/{self.repo}"
            f"/actions/workflows/{self.delete_workflow_file}/dispatches"
        )
        r2 = requests.post(
            url_wf,
            json={"ref": self.ref, "inputs": {"domain": domain, "slug": slug}},
            headers=self._headers,
            timeout=30,
        )
        if r2.status_code not in (201, 204):
            raise RuntimeError(
                f"Falha ao disparar delete (repo_dispatch={r.status_code}, "
                f"workflow_dispatch={r2.status_code} {r2.text})"
            )
