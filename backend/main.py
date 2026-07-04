from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routers import catalogo, config, historico, ingestao, lista, status

app = FastAPI(title="Home Bispo")

for router in (status.router, catalogo.router, lista.router, config.router, historico.router, ingestao.router):
    app.include_router(router, prefix="/api")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
