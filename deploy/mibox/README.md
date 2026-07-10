# Deploy na Mi Box (Android TV) via Termux

Pré-requisito: zona `fbsp.com.br` já ativa no Cloudflare (nameservers apontados, status "Active" no dashboard).

## Fase 1 — Termux

1. Instalar **Termux** e **Termux:Boot** pela **F-Droid** (a versão da Play Store está descontinuada e não recebe mais updates).
   - https://f-droid.org/packages/com.termux/
   - https://f-droid.org/packages/com.termux.boot/
2. Abrir o Termux e conceder as permissões pedidas (armazenamento, se solicitado).
3. Atualizar pacotes e instalar dependências básicas:
   ```sh
   pkg update && pkg upgrade -y
   pkg install -y git python
   ```

## Fase 2 — Clonar o repo e montar o venv

```sh
cd ~
git clone https://github.com/leonrd2312/home-bispo.git
cd home-bispo
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Se o repo for privado, o `git clone` vai pedir usuário/senha — use um Personal Access Token do GitHub no lugar da senha.

Configurar o `.env`:
```sh
cp .env.example .env
# editar e preencher ANTHROPIC_API_KEY
```

## Fase 3 — Testar manualmente antes de automatizar

```sh
.venv/bin/alembic upgrade head
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
Confirmar que abre em `http://<ip-da-mibox>:8000` na rede local. `Ctrl+C` pra parar depois de confirmar.

## Fase 4 — Instalar o cloudflared

Termux não tem `cloudflared` no `pkg`. Baixar o binário ARM direto do GitHub:

```sh
uname -m   # confirma a arquitetura: aarch64 (mais comum em Mi Box) ou arm
curl -L -o cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64
# se uname -m der "armv7l" ou "arm", trocar arm64 por arm no nome do arquivo acima
chmod +x cloudflared
mv cloudflared $PREFIX/bin/cloudflared
cloudflared --version
```

## Fase 5 — Criar o túnel

```sh
cloudflared tunnel login
```
Isso imprime uma URL no terminal — abra em qualquer navegador (celular/PC), faça login na conta Cloudflare e autorize o domínio `fbsp.com.br`. O Termux salva o certificado em `~/.cloudflared/cert.pem`.

```sh
cloudflared tunnel create homebispo
```
Anota o `<TUNNEL_ID>` que aparece no output (também vira o nome do arquivo `~/.cloudflared/<TUNNEL_ID>.json`).

Editar `deploy/mibox/cloudflared-config.yml` e substituir `<TUNNEL_ID>` nas duas linhas (`tunnel:` e `credentials-file:`) pelo ID gerado.

## Fase 6 — Apontar o DNS pro túnel

Só funciona se a zona já estiver "Active":
```sh
cloudflared tunnel route dns homebispo casa.fbsp.com.br
```
Isso cria o CNAME automaticamente — não precisa mexer no dashboard.

## Fase 7 — Testar o túnel manualmente

Com o uvicorn ainda rodando (repetir Fase 3 em outra sessão do Termux, ou rodar em background com `&`):
```sh
cloudflared tunnel --config deploy/mibox/cloudflared-config.yml run
```
Acessar `https://casa.fbsp.com.br` de fora da rede local (ex: dados móveis) pra confirmar que chega no FastAPI.

## Fase 8 — Configurar Access Application (Zero Trust)

No dashboard Cloudflare → Zero Trust → Access → Applications → **Add an application** → Self-hosted:
- Domain: `casa.fbsp.com.br`
- Policy: permitir só os e-mails da família (Leo + Jessica) via "One-time PIN" ou login social.

## Fase 9 — Automatizar com Termux:Boot

```sh
mkdir -p ~/.termux/boot
cp deploy/mibox/termux-boot.sh ~/.termux/boot/start-homebispo.sh
chmod +x ~/.termux/boot/start-homebispo.sh
```
Reiniciar a Mi Box e conferir os logs em `~/home-bispo/logs/` (`uvicorn.log`, `cloudflared.log`, `alembic.log`).

## Riscos conhecidos

- **Termux:Boot não dispara em todo firmware de Android TV** (fabricantes customizam agressivamente o battery/app killer). Se não subir sozinho após reboot, verificar se a Mi Box está exigindo abrir o Termux:Boot manualmente uma vez, e desativar otimização de bateria pro Termux e Termux:Boot nas configs do Android.
- **`pillow` pode enfrentar o mesmo problema que o `pymupdf` enfrentou** (sem wheel pronta pra Termux, compilação do zero pode falhar por falta de header/lib ou memória). Se travar na Fase 2, tentar `pkg install -y python-pillow` (pacote pré-compilado do próprio Termux) e recriar o venv com `python -m venv .venv --system-site-packages` antes do `pip install -r requirements.txt`, pra reaproveitar esse Pillow em vez de compilar via pip.
