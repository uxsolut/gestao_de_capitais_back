import os
import requests

class GitHubPagesDeployer:
    def __init__(self):
        self.owner = os.getenv("GITHUB_OWNER")
        self.repo = os.getenv("GITHUB_REPO")
        self.ref = os.getenv("GITHUB_REF", "main")
        self.workflow_file = os.getenv("WORKFLOW_FILE", "deploy-landing.yml")
        self.token = os.getenv("GITHUB_TOKEN_PAGES")

        # DELETE: nomes com defaults
        self.delete_workflow_file = os.getenv("DELETE_WORKFLOW_FILE", "delete-landing.yml")
        self.delete_event = os.getenv("DELETE_EVENT", "delete-landing")  # para repository_dispatch

        if not all([self.owner, self.repo, self.workflow_file, self.token]):
            raise RuntimeError("Defina GITHUB_OWNER, GITHUB_REPO, WORKFLOW_FILE e GITHUB_TOKEN_PAGES.")

        self._headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }

    def dispatch(self, *, domain: str, slug: str, zip_url: str) -> None:
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/actions/workflows/{self.workflow_file}/dispatches"
        payload = {
            "ref": self.ref,
            "inputs": {
                "domain": domain,   # <- nomes que o workflow espera
                "slug": slug,
                "zip_url": zip_url,
            }
        }
        r = requests.post(url, json=payload, headers=self._headers, timeout=30)
        if r.status_code not in (201, 204):
            raise RuntimeError(f"Falha ao disparar workflow ({r.status_code}): {r.text}")

    # NOVO: dispara o workflow de delete
    def dispatch_delete(self, *, domain: str, slug: str) -> None:
        """
        Tenta primeiro repository_dispatch (event_type=DELETE_EVENT).
        Se o repo não aceitar, faz workflow_dispatch no arquivo DELETE_WORKFLOW_FILE
        com inputs (domain, slug).
        """
        # 1) repository_dispatch
        url_repo_dispatch = f"https://api.github.com/repos/{self.owner}/{self.repo}/dispatches"
        payload_repo = {"event_type": self.delete_event,
                        "client_payload": {"domain": domain, "slug": slug}}
        r = requests.post(url_repo_dispatch, json=payload_repo, headers=self._headers, timeout=30)
        if r.status_code == 204:
            return  # ok via repository_dispatch

        # 2) fallback: workflow_dispatch
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
