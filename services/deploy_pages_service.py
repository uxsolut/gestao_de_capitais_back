# -*- coding: utf-8 -*-
import base64
import os
import uuid
import requests
from typing import Dict


class GitHubPagesDeployer:
    """
    Integra com o MESMO repositório do seu workflow:
      - envia o ZIP via Contents API (para uploads/…)
      - dispara o workflow existente com inputs: domain, slug, kind=zip_repo, zip_path

    ENV requeridos:
      GITHUB_OWNER
      GITHUB_REPO
      GITHUB_TOKEN_PAGES  (PAT com scopes: repo, workflow)
      GITHUB_REF          (branch, ex.: main)
      WORKFLOW_FILE       (ex.: 'deploy-landing.yml')  # nome do seu arquivo
    """
    def __init__(self) -> None:
        self.owner = os.getenv("GITHUB_OWNER")
        self.repo = os.getenv("GITHUB_REPO")
        self.token = os.getenv("GITHUB_TOKEN_PAGES")
        self.ref = os.getenv("GITHUB_REF", "main")
        self.workflow_file = os.getenv("WORKFLOW_FILE", "deploy-landing.yml")

        if not all([self.owner, self.repo, self.token]):
            raise RuntimeError("Defina GITHUB_OWNER, GITHUB_REPO e GITHUB_TOKEN_PAGES.")

        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        self.api_base = f"https://api.github.com/repos/{self.owner}/{self.repo}"

    # ---------- Upload ZIP para o repositório ----------
    def upload_zip(self, raw_zip: bytes, domain: str, slug: str) -> str:
        """
        Salva o zip em uploads/<domain>/<slug>-<id>.zip dentro do repo.
        Retorna o caminho relativo (zip_path) a ser passado ao workflow.
        """
        file_id = (str(uuid.uuid4())[:8])
        path = f"uploads/{domain}/{slug}-{file_id}.zip"

        content_b64 = base64.b64encode(raw_zip).decode("utf-8")
        url = f"{self.api_base}/contents/{path}"
        payload = {
            "message": f"upload: {domain}/p/{slug}",
            "content": content_b64,
            "branch": self.ref,
        }
        r = self._session.put(url, json=payload, timeout=60)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Falha no upload para GitHub ({r.status_code}): {r.text}")
        return path

    # ---------- Disparar workflow existente ----------
    def dispatch_workflow_zip_repo(self, *, domain: str, slug: str, zip_path: str) -> None:
        """
        Dispara seu workflow com inputs esperados.
        """
        url = f"{self.api_base}/actions/workflows/{self.workflow_file}/dispatches"
        payload = {
            "ref": self.ref,
            "inputs": {
                "domain": domain,
                "slug": slug,
                "kind": "zip_repo",
                "zip_path": zip_path,
                # os demais inputs (repo/ref/subdir/zip_url) são opcionais e não usados em zip_repo
            },
        }
        r = self._session.post(url, json=payload, timeout=30)
        if r.status_code != 204:
            raise RuntimeError(f"Falha ao disparar workflow ({r.status_code}): {r.text}")

    # ---------- URL final ----------
    @staticmethod
    def build_final_url(domain: str, slug: str, base_url_map: Dict[str, str] | None = None) -> str:
        """
        Monta a URL final seguindo seu Nginx (/p/<slug>/).
        Se base_url_map for fornecido, usa o mapeamento. Senão, assume https://<domain>.
        """
        if base_url_map and domain in base_url_map:
            base = base_url_map[domain]
        else:
            base = f"https://{domain}"
        return f"{base.rstrip('/')}/p/{slug}/"
