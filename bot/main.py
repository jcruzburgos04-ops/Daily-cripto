"""Punto de entrada: python -m bot [--test | --estado | --chat-id]"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import time
from datetime import datetime, timedelta, timezone

from . import fmt, summary
from .config import Config, load_config
from .detectors.ash import AshDetector
from .detectors.emas import EmaDetector
from .detectors.moves import MoveDetector
from .market import Market
from .state import State
from .telegram import Telegram

log = logging.getLogger("bot")

HELP = (
    "🤖 <b>Comandos</b>\n"
    "/estado — resumen actual de todos los activos\n"
    "/estado BTC ETH — sólo esos activos\n"
    "/cierre — el resumen de cierre diario, ahora\n"
    "/config — qué estoy vigilando\n"
    "/ping — ¿estás vivo?"
)


class Bot:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        g = cfg.general
        self.market = Market(g["exchanges"], g["quote"], cfg.symbols, int(g["history"]))
        self.state = State(g["state_file"])
        self.tg = Telegram(cfg.telegram_token, cfg.telegram_chat_id)
        self.moves = MoveDetector(cfg, self.market, self.state)
        self.emas = EmaDetector(cfg, self.market, self.state)
        self.ash = AshDetector(cfg, self.market, self.state)
        self.started = time.time()
        self.last_ok = time.time()

    # ── ciclo principal ──────────────────────────────────────────────────────
    async def tick(self) -> None:
        for det in (self.moves, self.emas, self.ash):
            try:
                for msg in await det.check():
                    await self.tg.send(msg)
            except Exception:  # noqa: BLE001
                log.exception("Error en %s", type(det).__name__)
        self.state.save()

    async def monitor_loop(self) -> None:
        period = float(self.cfg.general["poll_seconds"])
        while True:
            t0 = time.monotonic()
            await self.tick()
            await asyncio.sleep(max(1.0, period - (time.monotonic() - t0)))

    def next_summary_at(self, now: datetime) -> datetime:
        hh, mm = (int(x) for x in str(self.cfg.summary["time_utc"]).split(":"))
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        return target if target > now else target + timedelta(days=1)

    async def summary_loop(self) -> None:
        if not self.cfg.summary["enabled"]:
            return
        while True:
            now = datetime.now(timezone.utc)
            target = self.next_summary_at(now)
            await asyncio.sleep((target - now).total_seconds())
            day = target.strftime("%Y-%m-%d")
            if self.state.get("summary:last") == day:
                continue
            try:
                await self.tg.send(await summary.build(self.cfg, self.market, closing=True))
                self.state.set("summary:last", day)
                self.state.save()
            except Exception:  # noqa: BLE001
                log.exception("Error armando el resumen de cierre")

    # ── comandos ─────────────────────────────────────────────────────────────
    async def on_command(self, text: str, chat: str) -> None:
        parts = text.split()
        cmd = parts[0].split("@")[0].lower()
        args = [p.upper() for p in parts[1:]]
        if cmd in ("/start", "/ayuda", "/help"):
            await self.tg.send(HELP, chat)
        elif cmd == "/ping":
            up = (time.time() - self.started) / 3600
            await self.tg.send(f"🏓 Vivo hace {up:.1f} h", chat)
        elif cmd == "/estado":
            await self.tg.send(await summary.build(self.cfg, self.market, closing=False, only=args or None), chat)
        elif cmd == "/cierre":
            await self.tg.send(await summary.build(self.cfg, self.market, closing=True, only=args or None), chat)
        elif cmd == "/config":
            await self.tg.send(self.describe(), chat)
        else:
            await self.tg.send("No conozco ese comando.\n\n" + HELP, chat)

    def describe(self) -> str:
        m = self.cfg.moves
        wins = ", ".join(f"±{w['pct']}% en ≤{w['minutes']} min" for w in m["windows"])
        lines = ["⚙️ <b>Qué vigilo</b>"]
        for g in self.cfg.groups:
            lines.append(f"\n<b>{g.name}</b>: {', '.join(g.assets)}")
            if g.moves:
                lines.append(f"  • Movimientos: {wins} (umbrales de {m['reference']}; el resto ajustado por ATR)")
            if g.ema_timeframes:
                feats = [x for x, on in (("toques EMA100/200", g.ema_touch), ("nube 100/200", g.ema_cloud), ("cruces 21/34", g.ema_cross)) if on]
                lines.append(f"  • EMAs {', '.join(g.ema_timeframes)}: {', '.join(feats)}")
            if g.ash_timeframes:
                lines.append(f"  • ASH {', '.join(g.ash_timeframes)}" + (" (dirección y color)" if g.ash_color_changes else " (dirección)"))
        lines.append(f"\nResumen diario: {self.cfg.summary['time_utc']} UTC")
        routes = []
        for a in self.cfg.all_assets:
            try:
                routes.append(f"{a}: {self.market.source(a)}")
            except LookupError as e:
                routes.append(f"{a}: ⚠️ {e}")
        lines.append("\n<i>" + "\n".join(fmt.esc(r) for r in routes) + "</i>")
        return "\n".join(lines)

    # ── arranque ─────────────────────────────────────────────────────────────
    async def run(self) -> None:
        await self.market.start()
        missing = []
        for a in self.cfg.all_assets:
            try:
                self.market.resolve(a)
            except LookupError as e:
                missing.append(str(e))
                log.error("%s", e)
        if self.cfg.general["startup_message"]:
            msg = "✅ <b>Bot de alertas iniciado</b>\n\n" + self.describe()
            if missing:
                msg += "\n\n⚠️ Sin datos para:\n" + "\n".join(fmt.esc(m) for m in missing)
            await self.tg.send(msg)
        tasks = [
            asyncio.create_task(self.monitor_loop()),
            asyncio.create_task(self.summary_loop()),
            asyncio.create_task(self.tg.poll_commands(self.on_command)),
        ]
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:  # Windows
                pass
        await stop.wait()
        log.info("Apagando…")
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.shutdown()

    async def shutdown(self) -> None:
        self.state.save()
        await self.market.close()
        await self.tg.close()


async def _one_shot(cfg: Config, what: str) -> None:
    bot = Bot(cfg)
    try:
        if what == "chat-id":
            if not cfg.telegram_token:
                print("Falta TELEGRAM_BOT_TOKEN en .env")
                return
            chats = await bot.tg.discover_chats()
            if not chats:
                print("No encontré mensajes. Mandale cualquier mensaje a tu bot en Telegram y volvé a correr esto.")
            for cid, name in chats:
                print(f"TELEGRAM_CHAT_ID={cid}    ({name})")
            return
        await bot.market.start()
        if what == "test":
            await bot.tg.send("✅ Mensaje de prueba del bot de alertas.\n\n" + bot.describe())
        elif what == "estado":
            await bot.tg.send(await summary.build(cfg, bot.market, closing=False))
    finally:
        await bot.shutdown()


def main() -> None:
    ap = argparse.ArgumentParser(description="Bot de alertas cripto para Telegram")
    ap.add_argument("-c", "--config", default="config.yaml")
    ap.add_argument("--test", action="store_true", help="manda un mensaje de prueba y sale")
    ap.add_argument("--estado", action="store_true", help="manda el estado actual y sale")
    ap.add_argument("--chat-id", action="store_true", help="muestra el chat_id de quien le escribió al bot")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("ccxt").setLevel(logging.WARNING)
    cfg = load_config(args.config)
    if not cfg.telegram_token or not cfg.telegram_chat_id:
        log.warning("Sin TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID: los mensajes se imprimen por consola")
    if args.chat_id:
        asyncio.run(_one_shot(cfg, "chat-id"))
    elif args.test:
        asyncio.run(_one_shot(cfg, "test"))
    elif args.estado:
        asyncio.run(_one_shot(cfg, "estado"))
    else:
        asyncio.run(Bot(cfg).run())


if __name__ == "__main__":
    main()
