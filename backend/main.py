from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from .routers import catalogo, config, historico, ingestao, lista, status

app = FastAPI(title="Home Bispo")

for router in (status.router, catalogo.router, lista.router, config.router, historico.router, ingestao.router):
    app.include_router(router, prefix="/api")

# Gerado no build (ver Dockerfile) a partir da contagem de commits do git --
# "dev" quando rodado fora do Docker (ex: uvicorn direto num venv local).
VERSAO_PATH = Path(__file__).resolve().parent.parent / "versao.txt"
VERSAO = VERSAO_PATH.read_text().strip() if VERSAO_PATH.exists() else "dev"


@app.get("/api/versao")
def obter_versao():
    return {"versao": VERSAO}


class RevalidateStaticFiles(StaticFiles):
    """Impede qualquer cache de JS/CSS/HTML — nem no navegador, nem em CDN
    na frente (ex: Cloudflare). `no-cache` sozinho só exige revalidação
    condicional (If-None-Match), o que alguns navegadores mobile e proxies
    intermediários não respeitam de forma confiável; `no-store` + o combo
    de cabeçalhos legados abaixo é a forma que realmente força buscar a
    versão nova a cada deploy, sem depender de Purge manual de cache."""

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", RevalidateStaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
