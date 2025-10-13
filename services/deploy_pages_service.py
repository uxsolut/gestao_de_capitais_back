# services/deploy_pages_service.py
# -*- coding: utf-8 -*-
import os
import logging
import requests
from typing import Optional

log = logging.getLogger("deploy")

class GitHubPagesDeployer:
    """
    Mantemos o nome pra não mexer nos imports dos routers.
    Se DEPLOY_TARGET=runner -> chama o orquestrador local.
    Caso contrário, usa o fluxo GitHub legado.
    """

    def __init__(self):
        # --- Seleção do alvo ---
        self.target = os.getenv("DEPLOY_TARGET", "github").lower()

        # --- Runner (novo) ---
        self.runner_base = os.getenv("DEPLOY_RUNNER_BASE", "http://127.0.0.1:9501").rstrip("/")
        self.runner_token = os.getenv("DEPLOY_RUNNER_TOKEN", "")

        # --- GitHub (legado) ---
        self.owner = os.getenv("GITHUB_OWNER")
        self.repo = os.getenv("GITHUB_REPO")
        self.ref = os.getenv("GITHUB_REF", "main")
        self.workflow_file = os.getenv("WORKFLOW_FILE", "deploy-landing.yml")
        self.token = os.getenv("GITHUB_TOKEN_PAGES")
        self.delete_workflow_file = os.getenv("DELETE_WORKFLOW_FILE", "delete-landing.yml")
        self.delete_event = os.getenv("DELETE_EVENT", "delete-landing")

        # Sessão HTTP compartilhada
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json, */*"})
        # Header de auth do runner (quando usado)
        if self.runner_token:
            self.session.headers.update({"Authorization": f"Bearer {self.runner_token}"})

        # Validação só quando alvo = github
        if self.target != "runner":
            if not all([self.owner, self.repo, self.workflow_file, self.token]):
                raise RuntimeError("Defina GITHUB_OWNER, GITHUB_REPO, WORKFLOW_FILE e GITHUB_TOKEN_PAGES.")
            self._gh_headers = {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
            }

    # ================== API usada pelos routers ==================
    def dispatch(
        self,
        *,
        domain: str,
        slug: str,                     # "", "dev", "beta/x", "x"
        zip_url: str,
        empresa: Optional[str] = None, # já minúsculo
        id_empresa: Optional[int] = None,
        aplicacao_id: Optional[int] = None,
        api_base: Optional[str] = None,
        # compat futuros:
        commit: str = "",
        api_token: str = "",
        cancel_in_progress: bool = True,
    ):
        if self.target == "runner":
            return self._runner_dispatch(
                domain=domain,
                slug=slug or "",
                zip_url=zip_url,
                empresa=empresa or "",
                aplicacao_id=int(aplicacao_id) if aplicacao_id is not None else None,
                api_base=api_base or "",
                commit=commit or "",
                api_token=api_token or "",
                cancel_in_progress=bool(cancel_in_progress),
            )
        else:
            return self._github_dispatch(
                domain=domain,
                slug=slug,
                zip_url=zip_url,
                empresa=empresa,
                id_empresa=id_empresa,
                aplicacao_id=aplicacao_id,
                api_base=api_base,
            )

    def dispatch_delete(self, *, domain: str, slug: str):
        if self.target == "runner":
            # Seu runner atual não expõe delete. Logamos e seguimos.
            log.warning("Delete solicitado (%s/%s), mas o runner não possui endpoint de delete.", domain, slug)
            return {"ok": False, "detail": "delete_not_supported_by_runner"}
        else:
            return self._github_delete(domain=domain, slug=slug)

    # ================== Implementação Runner ==================
    def _runner_dispatch(
        self,
        *,
        domain: str,
        slug: str,
        zip_url: str,
        empresa: str,
        aplicacao_id: Optional[int],
        api_base: str,
        commit: str,
        api_token: str,
        cancel_in_progress: bool,
    ):
        payload = {
            "commit": commit,
            "api_token": api_token,
            "domain": domain,
            "slug": slug,
            "empresa": empresa,
            "zip_url": zip_url,
            "aplicacao_id": aplicacao_id,
            "api_base": api_base,
            "cancel_in_progress": cancel_in_progress,
        }
        # Remove chaves None pra não confundir o pydantic do runner
        payload = {k: v for k, v in payload.items() if v is not None}

        url = f"{self.runner_base}/deploy/landing"
        resp = self.session.post(url, json=payload, timeout=60)
        try:
            data = resp.json()
        except Exception:
            data = {"status_code": resp.status_code, "text": resp.text}

        if resp.status_code >= 400:
            raise RuntimeError(f"Runner dispatch falhou ({resp.status_code}): {data}")
        return data

    # ================== Implementação GitHub (legado) ==================
    def _github_dispatch(
        self,
        *,
        domain: str,
        slug: str,
        zip_url: str,
        empresa: Optional[str],
        id_empresa: Optional[int],
        aplicacao_id: Optional[int],
        api_base: Optional[str],
    ):
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
        if aplicacao_id is not None:
            inputs["aplicacao_id"] = str(aplicacao_id)
        if api_base:
            inputs["api_base"] = api_base

        r = self.session.post(url, json={"ref": self.ref, "inputs": inputs},
                              headers=self._gh_headers, timeout=30)
        if r.status_code not in (201, 204):
            raise RuntimeError(f"Falha ao disparar workflow ({r.status_code}): {r.text}")
        return {"ok": True, "via": "github", "status_code": r.status_code}

    def _github_delete(self, *, domain: str, slug: str):
        url_repo = f"https://api.github.com/repos/{self.owner}/{self.repo}/dispatches"
        r = self.session.post(
            url_repo,
            json={"event_type": self.delete_event, "client_payload": {"domain": domain, "slug": slug}},
            headers=self._gh_headers,
            timeout=30,
        )
        if r.status_code == 204:
            return {"ok": True, "via": "github", "mode": "repository_dispatch"}

        url_wf = (
            f"https://api.github.com/repos/{self.owner}/{self.repo}"
            f"/actions/workflows/{self.delete_workflow_file}/dispatches"
        )
        r2 = self.session.post(
            url_wf,
            json={"ref": self.ref, "inputs": {"domain": domain, "slug": slug}},
            headers=self._gh_headers,
            timeout=30,
        )
        if r2.status_code not in (201, 204):
            raise RuntimeError(
                f"Falha ao disparar delete (repo_dispatch={r.status_code}, "
                f"workflow_dispatch={r2.status_code} {r2.text})"
            )
        return {"ok": True, "via": "github", "mode": "workflow_dispatch"}
