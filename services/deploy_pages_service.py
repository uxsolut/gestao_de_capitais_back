# services/deploy_pages_service.py
import os, requests
from typing import Optional

class GitHubPagesDeployer:
    def __init__(self):
        self.owner = os.getenv("GITHUB_OWNER")
        self.repo = os.getenv("GITHUB_REPO")
        self.ref = os.getenv("GITHUB_REF", "main")
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
        slug: str,              # "", "dev", "beta/x", "x" (SEM empresa)
        zip_url: str,
        empresa: Optional[str] = None,   # <- nome pronto (minúsculo)
        id_empresa: Optional[int] = None # opcional p/ auditoria
    ) -> None:
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/actions/workflows/{self.workflow_file}/dispatches"
        inputs = {"domain": domain, "slug": slug, "zip_url": zip_url}
        if empresa:
            inputs["empresa"] = empresa
        if id_empresa is not None:
            inputs["id_empresa"] = str(id_empresa)
        r = requests.post(url, json={"ref": self.ref, "inputs": inputs}, headers=self._headers, timeout=30)
        if r.status_code not in (201, 204):
            raise RuntimeError(f"Falha ao disparar workflow ({r.status_code}): {r.text}")

    def dispatch_delete(self, *, domain: str, slug: str) -> None:
        url_repo = f"https://api.github.com/repos/{self.owner}/{self.repo}/dispatches"
        r = requests.post(url_repo, json={"event_type": self.delete_event, "client_payload": {"domain": domain, "slug": slug}}, headers=self._headers, timeout=30)
        if r.status_code == 204:
            return
        url_wf = f"https://api.github.com/repos/{self.owner}/{self.repo}/actions/workflows/{self.delete_workflow_file}/dispatches"
        r2 = requests.post(url_wf, json={"ref": self.ref, "inputs": {"domain": domain, "slug": slug}}, headers=self._headers, timeout=30)
        if r2.status_code not in (201, 204):
            raise RuntimeError(f"Falha ao disparar delete (repo_dispatch={r.status_code}, workflow_dispatch={r2.status_code} {r2.text})")
