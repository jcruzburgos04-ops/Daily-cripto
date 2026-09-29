# Daily-cripto — bot de alertas de BTC, ETH y altcoins en Telegram

Bot que está conectado todo el tiempo al mercado (APIs públicas de Binance / Bybit / OKX, no hace falta cuenta) y te avisa por Telegram cuando pasa algo importante, además de mandarte un resumen al cierre diario.

## Qué avisa

### BTC y ETH (grupo `principales`)
| Alerta | Cuándo |
|---|---|
| ⚡ Movimiento brusco | BTC sube o baja **≥1% en ≤5 min**, **≥3% en ≤30 min**, **≥5% en ≤1 h**. Son mínimos: si sigue, vuelve a avisar en cada múltiplo (x2, x3…). |
| ⚡ Movimiento en ETH | Mismos umbrales **multiplicados por su ATR relativo** (ATR% diario de ETH ÷ ATR% de BTC). Si ETH se mueve 1,4× lo que BTC, su umbral de 5 min es 1,4%. |
| 🎯 Toque de EMA 100 / 200 | La vela diaria en curso toca la EMA diaria (se revisa cada minuto, avisa en el momento). Dice si viene desde arriba (soporte) o desde abajo (resistencia). |
| ☁️ Nube EMA100–EMA200 | Entra, sale, se acerca (a menos de 0,5 ATR) o la cruza. **Mientras siga dentro o cerca, manda un recordatorio** con cuántas velas tocaron la nube, cuántas cerraron adentro y cuántas veces cambió de lado. También avisa cuando la EMA100 cruza la 200 (la nube cambia de color). |
| 🔄 ASH semanal / mensual | Cambia de dirección (▲↔▼) o de color (gana/pierde fuerza). |

### Altcoins (grupo `alts`): UNI, AAVE, XPL, LINK, AVAX, ONDO, HYPE
- 🎯 Toques de la EMA 100 / 200 diaria
- ✅❌ Cruces de la EMA 21 y 34 diaria (sólo con vela cerrada)
- 🔄 Cambios del ASH semanal / mensual

### 🌙 Resumen al cierre
Todos los días a las 00:05 UTC (21:05 en Argentina): precio y variación del día, posición contra la nube, EMA 21 vs 34 y estado del ASH diario / semanal / mensual de cada activo. Los lunes incluye el cierre semanal y el día 1 el mensual (y marca si el ASH cambió respecto a la vela anterior).

### Comandos en Telegram
`/estado` · `/estado BTC ETH` · `/cierre` · `/config` · `/ping`

## Cómo se calculan los indicadores

Se replica la matemática de Pine Script para que coincida con lo que ves en TradingView:

- **EMA**: `ta.ema` (alpha = 2/(n+1), arranca con la SMA de las primeras n velas). Las EMAs 21 / 34 / 100 / 200 son **diarias**. Si agregás otro timeframe en `ema_timeframes`, el largo se adapta solo para que sea la misma línea: en 4H ×6 (21→126, 34→204, 100→600, 200→1200), en 1H ×24. Se baja historia suficiente (4× el largo de la EMA más larga) para que converjan.
- **ASH v2**: modo RSI, Length 16, Smooth 4, media EMA (tu configuración). `Bulls = EMA(EMA(max(Δ,0), 16), 4)`, `Bears` igual con la caída. Dirección ▲ si Bulls ≥ Bears. Color como el indicador: 🟢 verde (alcista, Bulls subiendo), 🟩 lime (alcista, Bulls bajando), 🔴 rojo (bajista, Bears subiendo), 🟠 naranja (bajista, Bears bajando).
- Igual que el cuadro MTF, el ASH semanal/mensual se mira sobre la **vela en curso**. Para no avisar cambios que se deshacen enseguida, un cambio tiene que sostenerse 15 minutos (`ash.confirm_minutes`).
- **ATR**: `ta.atr(14)` (RMA del true range).

Todo es configurable en [`config.yaml`](config.yaml) (umbrales, timeframes, activos, frecuencia de recordatorios, etc).

## Puesta en marcha

### 1. Crear el bot de Telegram
1. En Telegram hablale a **@BotFather** → `/newbot` → elegí nombre. Te da un **token**.
2. Copiá `.env.example` como `.env` y pegá el token en `TELEGRAM_BOT_TOKEN`.
3. Mandale cualquier mensaje a tu bot nuevo y corré:
   ```bash
   python -m bot --chat-id
   ```
   Te imprime `TELEGRAM_CHAT_ID=...`; pegalo en `.env`.
   (Si querés las alertas en un grupo, agregá el bot al grupo, escribí algo ahí y usá ese id, que empieza con `-`).

### 2. Probarlo en tu compu
```bash
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m bot --test             # manda un mensaje de prueba
python -m bot --estado           # manda el estado actual
python -m bot                    # arranca el bot (Ctrl+C para cortar)
```
Sin token en `.env` los mensajes se imprimen en la consola, útil para probar.

### 3. Dejarlo corriendo 24/7
📘 **Guía paso a paso para Oracle Cloud (gratis): [docs/ORACLE.md](docs/ORACLE.md)** — con un script que instala todo con un solo comando.

Para que funcione solo tiene que estar en un servidor prendido siempre. Opciones baratas o gratis: Oracle Cloud Free Tier, Hetzner, DigitalOcean, una Raspberry Pi en tu casa.

> ⚠️ Binance, Bybit y OKX **bloquean servidores ubicados en EE.UU.** Elegí un servidor en Europa, Asia o Sudamérica.

**Con Docker** (recomendado):
```bash
git clone <este repo> && cd Daily-cripto
cp .env.example .env && nano .env
docker compose up -d --build
docker compose logs -f           # ver qué está haciendo
```
Se reinicia solo si se cae o si se reinicia el servidor. El estado (qué ya avisó) se guarda en `data/state.json`, así no repite alertas al reiniciar.

**Sin Docker**: hay un servicio de systemd de ejemplo en [`deploy/cripto-bot.service`](deploy/cripto-bot.service).

## Agregar una altcoin
Sumala a `groups.alts.assets` en `config.yaml` y reiniciá (`docker compose restart`). El bot busca el par `XXX/USDT` en Binance, después Bybit y después OKX. Si querés forzar un exchange:
```yaml
symbols:
  HYPE: {exchange: bybit}
```
`/config` te muestra de qué exchange está sacando cada moneda.

## Tests
```bash
pip install pytest && pytest
```
