#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════════
#  Instala y arranca el bot de alertas en un servidor Ubuntu (ej. Oracle Cloud).
#
#  Uso (en el servidor):
#    curl -fsSL https://raw.githubusercontent.com/jcruzburgos04-ops/Daily-cripto/main/deploy/setup.sh | bash
#
#  Se puede volver a correr cuando quieras: actualiza el código y reinicia el
#  bot, sin tocar tu .env ni tu config.yaml.
# ════════════════════════════════════════════════════════════════════════════
set -euo pipefail

REPO="${REPO:-https://github.com/jcruzburgos04-ops/Daily-cripto.git}"
BRANCH="${BRANCH:-main}"
DIR="${DIR:-$HOME/Daily-cripto}"

say()  { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m⚠ %s\033[0m\n' "$*"; }

# Cuando el script llega por "curl | bash", el teclado no es stdin: leer de /dev/tty.
ask() {
  local prompt="$1" var
  read -r -p "$prompt" var < /dev/tty
  printf '%s' "$var"
}

# ── 1. Memoria swap (la máquina gratis chica tiene 1 GB de RAM) ─────────────
if [ "$(free -m | awk '/^Mem:/{print $2}')" -lt 2000 ] && ! swapon --show | grep -q .; then
  say "Creando 2 GB de swap (la máquina tiene poca RAM)"
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  ok "Swap activada"
fi

# ── 2. Actualizaciones de seguridad automáticas ────────────────────────────
say "Activando actualizaciones de seguridad automáticas"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git unattended-upgrades >/dev/null
echo 'APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";' | sudo tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null
ok "Listo"

# ── 3. Docker ──────────────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  say "Instalando Docker (instalador oficial)"
  curl -fsSL https://get.docker.com | sudo sh >/dev/null
  sudo systemctl enable --now docker
  ok "Docker instalado"
else
  ok "Docker ya estaba instalado"
fi
DOCKER="sudo docker"

# ── 4. Código del bot ──────────────────────────────────────────────────────
if [ -d "$DIR/.git" ]; then
  say "Actualizando el código"
  git -C "$DIR" fetch -q origin "$BRANCH"
  # Conserva tus cambios en config.yaml si los hubiera
  git -C "$DIR" stash -q || true
  git -C "$DIR" checkout -q "$BRANCH"
  git -C "$DIR" reset -q --hard "origin/$BRANCH"
  git -C "$DIR" stash pop -q 2>/dev/null || true
else
  say "Descargando el bot"
  git clone -q --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"
mkdir -p data
touch .env && chmod 600 .env   # docker compose lo necesita aunque esté vacío
ok "Código en $DIR"

say "Construyendo el bot (la primera vez tarda unos minutos)"
$DOCKER compose build -q
ok "Listo"

# ── 5. Datos de Telegram (.env) ────────────────────────────────────────────
if ! grep -qE '^TELEGRAM_CHAT_ID=.+' .env; then
  say "Configuración de Telegram"
  echo "Pegá el token que te dio @BotFather (se ve así: 123456789:AAH...)"
  TOKEN="$(ask 'Token: ')"
  printf 'TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=\n' "$TOKEN" > .env
  chmod 600 .env

  echo
  echo "Ahora abrí Telegram, buscá tu bot y mandale cualquier mensaje (por ejemplo: hola)."
  ask 'Cuando lo hayas mandado, apretá Enter… ' >/dev/null
  CHATS="$($DOCKER compose run --rm -T bot python -m bot --chat-id 2>/dev/null | grep '^TELEGRAM_CHAT_ID=' || true)"
  if [ -z "$CHATS" ]; then
    warn "No encontré tu mensaje. Revisá el token, mandale otro mensaje al bot y volvé a correr este script."
    : > .env
    exit 1
  fi
  echo "$CHATS"
  CHAT_ID="$(echo "$CHATS" | head -n1 | sed 's/^TELEGRAM_CHAT_ID=\([^ ]*\).*/\1/')"
  printf 'TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=%s\n' "$TOKEN" "$CHAT_ID" > .env
  chmod 600 .env
  ok "Chat configurado: $CHAT_ID"

  say "Mandando un mensaje de prueba a tu Telegram"
  if $DOCKER compose run --rm -T bot python -m bot --test >/dev/null 2>&1; then
    ok "¡Revisá Telegram, te tiene que haber llegado!"
  else
    warn "No pude mandar el mensaje de prueba. Mirá el error con:  cd $DIR && sudo docker compose run --rm bot python -m bot --test"
  fi
fi

# ── 6. Arrancar ────────────────────────────────────────────────────────────
say "Arrancando el bot"
$DOCKER compose up -d
ok "El bot está corriendo y se reinicia solo si se cae o si se reinicia el servidor."

cat <<EOF

Comandos útiles (entrá primero con:  cd $DIR)
  Ver qué está haciendo:   sudo docker compose logs -f --tail 50      (Ctrl+C para salir)
  Reiniciar:               sudo docker compose restart
  Cambiar la config:       nano config.yaml   y después reiniciar
  Actualizar el bot:       volvé a correr este script
EOF
