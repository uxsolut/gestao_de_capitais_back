# routers/media.py
# -*- coding: utf-8 -*-
import os, time, secrets
from io import BytesIO
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status
from PIL import Image
from auth.dependencies import get_current_user
from models.users import User

router = APIRouter(prefix="/media", tags=["Media"])

# Envs vindas do systemd
BASE_UPLOADS_DIR = os.getenv("BASE_UPLOADS_DIR", "/var/www/uploads")
BASE_UPLOADS_URL = os.getenv("BASE_UPLOADS_URL")

ALLOWED = {"image/jpeg", "image/png", "image/webp"}
TARGET_W, TARGET_H = 1200, 630          # padrão OG
MAX_FILE_SIZE = 10 * 1024 * 1024        # 10MB por arquivo
MAX_FILES     = 20                      # limite por requisição

def _ensure_dirs():
    if not BASE_UPLOADS_DIR or not BASE_UPLOADS_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BASE_UPLOADS_DIR/BASE_UPLOADS_URL não configurados.",
        )
    os.makedirs(os.path.join(BASE_UPLOADS_DIR, "og"), exist_ok=True)

def _read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    data = upload.file.read(max_bytes + 1)
    if not data:
        raise HTTPException(400, detail=f"Arquivo vazio: {upload.filename}")
    if len(data) > max_bytes:
        raise HTTPException(413, detail=f"{upload.filename} excede {max_bytes//(1024*1024)}MB.")
    return data

def _process_to_og(jpg_path: str, raw: bytes):
    im = Image.open(BytesIO(raw)).convert("RGB")
    src_w, src_h = im.size
    src_ratio = src_w / src_h
    tgt_ratio = TARGET_W / TARGET_H
    if src_ratio > tgt_ratio:
        new_h = TARGET_H
        new_w = int(round(new_h * src_ratio))
        im = im.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - TARGET_W) // 2
        im = im.crop((left, 0, left + TARGET_W, TARGET_H))
    else:
        new_w = TARGET_W
        new_h = int(round(new_w / src_ratio))
        im = im.resize((new_w, new_h), Image.LANCZOS)
        top = (new_h - TARGET_H) // 2
        im = im.crop((0, top, TARGET_W, top + TARGET_H))
    im.save(jpg_path, format="JPEG", quality=85, optimize=True, progressive=True)

@router.post("/upload-og-images")
def upload_og_images(
    files: List[UploadFile] = File(..., description="Envie 1..N arquivos no campo 'files'"),
    current_user: User = Depends(get_current_user),
):
    _ensure_dirs()
    if not files:
        raise HTTPException(400, "Nenhum arquivo enviado.")
    if len(files) > MAX_FILES:
        raise HTTPException(413, f"Máximo de {MAX_FILES} arquivos por requisição.")

    results, errors = [], []

    for f in files:
        if f.content_type not in ALLOWED:
            errors.append({"filename": f.filename, "error": "Formato inválido (JPG, PNG ou WEBP)."})
            continue
        try:
            raw = _read_limited(f, MAX_FILE_SIZE)
            ts = int(time.time())
            rid = secrets.token_hex(4)
            base_name = f"og-{ts}-{rid}"
            jpg_path = os.path.join(BASE_UPLOADS_DIR, "og", f"{base_name}.jpg")
            _process_to_og(jpg_path, raw)

            jpg_url = f"{BASE_UPLOADS_URL.rstrip('/')}/og/{base_name}.jpg"
            results.append({
                "filename": f.filename,
                "og_image_url": jpg_url,
                "width": TARGET_W,
                "height": TARGET_H,
                "meta": {
                    "og:image": jpg_url,
                    "og:image:width": str(TARGET_W),
                    "og:image:height": str(TARGET_H),
                    "twitter:card": "summary_large_image",
                },
            })
        except HTTPException as he:
            errors.append({"filename": f.filename, "error": he.detail})
        except Exception as e:
            errors.append({"filename": f.filename, "error": f"Falha ao processar: {e}"})

    return {"ok": len(results) > 0, "count": len(results), "results": results, "errors": errors}
