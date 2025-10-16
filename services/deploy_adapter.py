# -*- coding: utf-8 -*-
import os
import requests
from typing import Optional
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
        self._headers_auth = {"Authorization": f"Bearer {self.token}"}
        # >>> base do deleter (default local)
        self.deleter_base = (os.getenv("DELETER_BASE") or "http://127.0.0.1:9103").rstrip("/")

    def _post_json(self, path: str, payload: dict):
        url = f"{self.base}{path}"
        r = requests.post(url, json=payload, headers=self._headers_json, timeout=60)
        if r.status_code >= 300:
            raise RuntimeError(f"Runner {path} falhou ({r.status_code}): {r.text}")
        return r

    def _post_upload(self, path: str, form: dict, zip_path: str):
        url = f"{self.base}{path}"
        with open(zip_path, "rb") as fh:
            files = {"arquivo_zip": ("release.zip", fh, "application/zip")}
            r = requests.post(url, data=form, files=files, headers=self._headers_auth, timeout=180)
        if r.status_code >= 300:
            raise RuntimeError(f"Runner {path} falhou ({r.status_code}): {r.text}")
        return r

    def dispatch(
        self,
        *,
        domain: str,
        slug: str,                # "", "dev", "beta/x", "x"
        zip_url: Optional[str] = None,
        zip_path: Optional[str] = None,   # << NOVO
        empresa: Optional[str] = None,
        id_empresa: Optional[int] = None,
        aplicacao_id: Optional[int] = None,
        api_base: Optional[str] = None,
    ) -> None:
        # Preferir upload se houver arquivo local
        if zip_path and os.path.exists(zip_path):
            self._post_upload(
                "/deploy/landing/upload",
                {
                    "domain": domain,
                    "slug": slug or "",
                    "empresa": (empresa or ""),
                    "aplicacao_id": int(aplicacao_id or 0),
                    "api_base": api_base or "",
                    "cancel_in_progress": "true",
                },
                zip_path,
            )
            return

        # Fallback: download por URL (legado)
        if not zip_url:
            raise RuntimeError("Faltou zip_url OU zip_path para deploy.")
        self._post_json(
            "/deploy/landing",
            {
                "commit": "",
                "api_token": "",
                "domain": domain,
                "slug": slug or "",
                "empresa": empresa or "",
                "zip_url": zip_url,
                "aplicacao_id": int(aplicacao_id or 0),
                "api_base": api_base or "",
                "cancel_in_progress": True,
            },
        )

    def dispatch_delete(self, *, domain: str, slug: str) -> None:
        # >>> AGORA CHAMA O DELETER
        url = f"{self.deleter_base}/deploy/delete-landing"
        payload = {"domain": domain, "slug": slug or ""}
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code >= 300:
            raise RuntimeError(f"Deleter falhou ({r.status_code}): {r.text}")


def get_deployer():
    target = (os.getenv("DEPLOY_TARGET") or "").strip().lower()
    if target == "runner":
        return RunnerDeployer()
    return GitHubPagesDeployer()
