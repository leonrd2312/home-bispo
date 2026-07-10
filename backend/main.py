from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from .routers import catalogo, config, historico, ingestao, lista, status

app = FastAPI(title="Home Bispo")

for router in (status.router, catalogo.router, lista.router, config.router, historico.router, ingestao.router):
    app.include_router(router, prefix="/api")


class RevalidateStaticFiles(StaticFiles):
    """Força o navegador a sempre revalidar (If-None-Match/If-Modified-Since)
    em vez de usar cache heurístico — evita servir JS/CSS desatualizados
    depois de um deploy, sem perder o benefício do 304 quando nada mudou."""

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", RevalidateStaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
