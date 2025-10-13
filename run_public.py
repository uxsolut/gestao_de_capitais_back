# run_public.py
import os
os.environ.setdefault("APP_MODE", "public")        # expõe só as rotas públicas
from main import create_app
app = create_app(os.getenv("APP_MODE", "public"))
