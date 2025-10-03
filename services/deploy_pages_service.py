import os
import requests
from typing import Optional

class GitHubPagesDeployer:
    def __init__(self):
        self.owner = os.getenv("GITHUB_OWNER")
        self.repo = os.getenv("GITHUB_REPO")
        self.ref = os.getenv("GITHUB_REF", "main")
        self.workflow_file = os.getenv("WORKFLOW_FILE", "deploy-landing.yml")
        self.token = os.getenv("GITHUB_TOKEN_PAGES")

        # DELETE: nomes com defaults
        self.delete_workflow_file = os.getenv("DELETE_WORKFLOW_FILE", "delete-landing.yml")
        self.delete_event = os.getenv("DELETE_EVENT", "delete-landing")  # repository_dispatch

        if not all([self.owner, self.repo, self.workflow_file, self.token]):
            raise RuntimeError("Defina GITHUB_OWNER, GITHUB_REPO, WORKFLOW_FILE e GITHUB_TOKEN_PAGES.")

        self._headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }

    def dispatch(self, *, domain: str, slug: str, zip_url: str, id_empresa: Optional[int] = None) -> None:
        """
        Dispara o workflow de deploy.
        - 'slug' aqui já deve ser o caminho montado (ex.: 'dev/pinacle/testelegal' ou 'pinacle').
        - Se 'id_empresa' vier, é repassado para o workflow (que resolve o nome/empresa na URL).
        """
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/actions/workflows/{self.workflow_file}/dispatches"
        inputs = {
            "domain": domain,   # nomes esperados pelo workflow
            "slug": slug,
            "zip_url": zip_url,
        }
        if id_empresa is not None:
            inputs["id_empresa"] = str(id_empresa)  # <-- essencial

        payload = {"ref": self.ref, "inputs": inputs}
        r = requests.post(url, json=payload, headers=self._headers, timeout=30)
        if r.status_code not in (201, 204):
            raise RuntimeError(f"Falha ao disparar workflow ({r.status_code}): {r.text}")

    def dispatch_delete(self, *, domain: str, slug: str) -> None:
        """
        Tenta repository_dispatch (event_type=DELETE_EVENT). Se não, usa workflow_dispatch.
        """
        url_repo_dispatch = f"https://api.github.com/repos/{self.owner}/{self.repo}/dispatches"
        payload_repo = {
            "event_type": self.delete_event,
            "client_payload": {"domain": domain, "slug": slug},
        }
        r = requests.post(url_repo_dispatch, json=payload_repo, headers=self._headers, timeout=30)
        if r.status_code == 204:
            return  # ok via repository_dispatch

        url_workflow_dispatch = (
            f"https://api.github.com/repos/{self.owner}/{self.repo}"
            f"/actions/workflows/{self.delete_workflow_file}/dispatches"
        )
        payload_wf = {"ref": self.ref, "inputs": {"domain": domain, "slug": slug}}
        r2 = requests.post(url_workflow_dispatch, json=payload_wf, headers=self._headers, timeout=30)
        if r2.status_code not in (201, 204):
            raise RuntimeError(
                f"Falha ao disparar delete "
                f"(repo_dispatch={r.status_code}, workflow_dispatch={r2.status_code} {r2.text})"
            )
