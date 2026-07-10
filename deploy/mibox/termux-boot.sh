#!/data/data/com.termux/files/usr/bin/sh
# Copiar para ~/.termux/boot/start-homebispo.sh e dar chmod +x
# (exige o app Termux:Boot instalado para rodar sozinho quando a Mi Box liga).

termux-wake-lock

REPO_DIR="$HOME/home-bispo"
LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"

cd "$REPO_DIR" || exit 1
set -a
. ./.env
set +a

"$REPO_DIR/.venv/bin/alembic" upgrade head >> "$LOG_DIR/alembic.log" 2>&1

nohup "$REPO_DIR/.venv/bin/uvicorn" backend.main:app --host 0.0.0.0 --port 8000 \
  >> "$LOG_DIR/uvicorn.log" 2>&1 &

nohup cloudflared tunnel --config "$REPO_DIR/deploy/mibox/cloudflared-config.yml" run \
  >> "$LOG_DIR/cloudflared.log" 2>&1 &
