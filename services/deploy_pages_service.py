import os
import requests

class GitHubPagesDeployer:
    def __init__(self):
        self.owner = os.getenv("GITHUB_OWNER")
        self.repo = os.getenv("GITHUB_REPO")
        self.ref = os.getenv("GITHUB_REF", "main")
        self.workflow_file = os.getenv("WORKFLOW_FILE", "deploy-landing.yml")
        self.token = os.getenv("GITHUB_TOKEN_PAGES")

        if not all([self.owner, self.repo, self.workflow_file, self.token]):
            raise RuntimeError("Defina GITHUB_OWNER, GITHUB_REPO, WORKFLOW_FILE e GITHUB_TOKEN_PAGES.")

    def dispatch(self, *, domain: str, slug: str, zip_url: str) -> None:
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/actions/workflows/{self.workflow_file}/dispatches"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }
        payload = {
            "ref": self.ref,
            "inputs": {
                "domain": domain,   # <- nomes que o workflow espera
                "slug": slug,
                "zip_url": zip_url,
            }
        }
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        if r.status_code not in (201, 204):
            raise RuntimeError(f"Falha ao disparar workflow ({r.status_code}): {r.text}")
