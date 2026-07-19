# Numero de versao = quantidade de commits no historico do git -- automatico,
# nunca exige lembrar de incrementar nada na mao, e retroativo desde o
# primeiro commit do projeto. So esse estagio tem git instalado; o estagio
# final abaixo fica sem ele (nao precisa, so consome o arquivo gerado aqui).
FROM alpine:3.20 AS versao
RUN apk add --no-cache git
WORKDIR /repo
COPY .git .git
RUN git rev-list --count HEAD > /versao.txt || echo "dev" > /versao.txt

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY alembic.ini .
COPY migrations/ migrations/
COPY --from=versao /versao.txt versao.txt

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.main:app --host 0.0.0.0 --port 8000"]
