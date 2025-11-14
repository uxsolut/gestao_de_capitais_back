# services/deploy_adapter.py
# -*- coding: utf-8 -*-
import os
import requests
from typing import Optional, Any
from services.deploy_pages_service import GitHubPagesDeployer


class RunnerDeployer:
    """Faz deploy via Runner local (/deploy/landing*, /deploy/fullstack*)."""
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

    # -------------------- helpers HTTP --------------------
    def _post_json(self, path: str, payload: dict):
        url = f"{self.base}{path}"
        r = requests.post(url, json=payload, headers=self._headers_json, timeout=180)
        if r.status_code >= 300:
            raise RuntimeError(f"Runner {path} falhou ({r.status_code}): {r.text}")
        return r

    def _post_upload(self, path: str, form: dict, zip_path: str):
        url = f"{self.base}{path}"
        with open(zip_path, "rb") as fh:
            files = {"arquivo_zip": ("release.zip", fh, "application/zip")}
            r = requests.post(url, data=form, files=files, headers=self._headers_auth, timeout=600)
        if r.status_code >= 300:
            raise RuntimeError(f"Runner {path} falhou ({r.status_code}): {r.text}")
        return r

    # -------------------- FRONTEND (já existente) --------------------
    def dispatch(
        self,
        *,
        domain: str,
        slug: str,                           # "", "dev", "beta/x", "x"
        zip_url: Optional[str] = None,
        zip_path: Optional[str] = None,      # suporta upload também
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

    # -------------------- FULLSTACK (NOVO) --------------------
    def dispatch_fullstack(
        self,
        *,
        domain: str,
        slug: str,
        zip_path: Optional[str],             # fullstack trabalha com upload local
        empresa: Optional[str],
        id_empresa: Optional[int],
        aplicacao_id: Any,
        api_base: str,                       # ex.: "/beta/pastel/api/"
        zip_url: Optional[str] = None,       # fallback opcional
    ) -> None:
        """
        Publica front + back. O Runner deve:
          - extrair o ZIP
          - separar frontend/ e backend/
          - publicar o frontend (mesma lógica do landing)
          - publicar o backend em <api_base>
        """

        # 1) Preferir upload (compatível com /fullstack/upload do Runner)
        if zip_path and os.path.exists(zip_path):
            self._post_upload(
                "/deploy/fullstack/upload",
                {
                    "domain": domain,
                    "slug": slug or "",
                    "empresa": (empresa or ""),
                    "id_empresa": int(id_empresa or 0),
                    "aplicacao_id": int(aplicacao_id or 0),
                    "api_base": api_base or "",
                    "cancel_in_progress": "true",
                },
                zip_path,
            )
            return

        # 2) Fallback JSON (se o Runner aceita ler um caminho local ou baixar por URL)
        if zip_path:
            self._post_json(
                "/deploy/fullstack",
                {
                    "domain": domain,
                    "slug": slug or "",
                    "zip_path": zip_path,
                    "empresa": (empresa or ""),
                    "id_empresa": int(id_empresa or 0),
                    "aplicacao_id": int(aplicacao_id or 0),
                    "api_base": api_base or "",
                    "cancel_in_progress": True,
                },
            )
            return

        if zip_url:
            self._post_json(
                "/deploy/fullstack",
                {
                    "domain": domain,
                    "slug": slug or "",
                    "zip_url": zip_url,
                    "empresa": (empresa or ""),
                    "id_empresa": int(id_empresa or 0),
                    "aplicacao_id": int(aplicacao_id or 0),
                    "api_base": api_base or "",
                    "cancel_in_progress": True,
                },
            )
            return

        raise RuntimeError("Faltou zip_path (recomendado) ou zip_url para deploy fullstack.")

    # -------------------- DELETE (já existente) --------------------
    def dispatch_delete(self, *, domain: str, slug: str) -> None:
        # >>> chama o deleter central
        url = f"{self.deleter_base}/deploy/delete-landing"
        payload = {"domain": domain, "slug": slug or ""}
        r = requests.post(url, json=payload, timeout=60)
        if r.status_code >= 300:
            raise RuntimeError(f"Deleter falhou ({r.status_code}): {r.text}")


def get_deployer():
    target = (os.getenv("DEPLOY_TARGET") or "").strip().lower()
    if target == "runner":
        return RunnerDeployer()
    return GitHubPagesDeployer()
