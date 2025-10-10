# routers/media.py
# -*- coding: utf-8 -*-
import os, time, secrets
from io import BytesIO
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status
from PIL import Image
from auth.dependencies import get_current_user
from models.users import User

router = APIRouter(prefix="/media", tags=["Media"])

# Lê das variáveis de ambiente definidas no systemd (override.conf)
BASE_UPLOADS_DIR = os.getenv("BASE_UPLOADS_DIR", "/var/www/uploads")
BASE_UPLOADS_URL = os.getenv("BASE_UPLOADS_URL")

ALLOWED = {"image/jpeg", "image/png", "image/webp"}
TARGET_W, TARGET_H = 1200, 630  # padrão OG
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def _ensure_dirs():
    if not BASE_UPLOADS_DIR or not BASE_UPLOADS_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BASE_UPLOADS_DIR/BASE_UPLOADS_URL não configurados."
        )
    os.makedirs(os.path.join(BASE_UPLOADS_DIR, "og"), exist_ok=True)

def _read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    data = upload.file.read(max_bytes + 1)
    if len(data) == 0:
        raise HTTPException(400, detail="Arquivo vazio.")
    if len(data) > max_bytes:
        raise HTTPException(413, detail=f"Arquivo excede {max_bytes//(1024*1024)}MB.")
    return data

@router.post("/upload-og-image")
def upload_og_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),  # proteja se quiser
):
    if file.content_type not in ALLOWED:
        raise HTTPException(400, detail="Formato inválido. Envie JPG, PNG ou WEBP.")

    _ensure_dirs()

    ts = int(time.time())
    rid = secrets.token_hex(4)
    base_name = f"og-{ts}-{rid}"
    jpg_path = os.path.join(BASE_UPLOADS_DIR, "og", f"{base_name}.jpg")

    try:
        raw = _read_limited(file, MAX_FILE_SIZE)
        im = Image.open(BytesIO(raw)).convert("RGB")

        # crop central proporcional 1200x630
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, detail=f"Falha ao processar imagem: {e}")

    jpg_url = f"{BASE_UPLOADS_URL.rstrip('/')}/og/{base_name}.jpg"
    return {
        "ok": True,
        "og_image_url": jpg_url,
        "width": TARGET_W,
        "height": TARGET_H,
        "meta": {
            "og:image": jpg_url,
            "og:image:width": str(TARGET_W),
            "og:image:height": str(TARGET_H),
            "twitter:card": "summary_large_image",
        },
    }
