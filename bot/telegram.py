"""Cliente mínimo de la Bot API de Telegram (enviar mensajes + leer comandos)."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import aiohttp

log = logging.getLogger(__name__)

MAX_LEN = 4000  # Telegram corta en 4096


def split_message(text: str, limit: int = MAX_LEN) -> list[str]:
    parts: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        parts.append(text)
    return parts


class Telegram:
    """Si no hay token, imprime los mensajes por consola (modo prueba)."""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = str(chat_id)
        self.base = f"https://api.telegram.org/bot{token}"
        self._session: aiohttp.ClientSession | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=70))
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def call(self, method: str, **params) -> dict:
        s = await self._sess()
        async with s.post(f"{self.base}/{method}", json=params) as r:
            data = await r.json(content_type=None)
            if not data.get("ok"):
                raise RuntimeError(f"Telegram {method}: {data}")
            return data

    async def send(self, text: str, chat_id: str | None = None) -> None:
        if not self.enabled:
            print("\n" + "─" * 60 + "\n" + text + "\n" + "─" * 60, flush=True)
            return
        for part in split_message(text):
            for attempt in range(5):
                try:
                    await self.call(
                        "sendMessage",
                        chat_id=chat_id or self.chat_id,
                        text=part,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    break
                except Exception as e:  # noqa: BLE001
                    wait = 2 ** attempt
                    if "retry_after" in str(e):
                        wait = max(wait, 30)
                    log.warning("Fallo enviando a Telegram (%s); reintento en %ss", e, wait)
                    await asyncio.sleep(wait)

    async def poll_commands(self, handler: Callable[[str, str], Awaitable[None]]) -> None:
        """Long-polling de getUpdates. Sólo atiende al chat configurado."""
        if not self.enabled:
            return
        offset = None
        while True:
            try:
                params = {"timeout": 50, "allowed_updates": ["message"]}
                if offset is not None:
                    params["offset"] = offset
                data = await self.call("getUpdates", **params)
                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    msg = upd.get("message") or {}
                    chat = str((msg.get("chat") or {}).get("id", ""))
                    text = (msg.get("text") or "").strip()
                    if not text.startswith("/"):
                        continue
                    if chat != self.chat_id:
                        log.info("Comando ignorado de un chat no autorizado (%s)", chat)
                        continue
                    await handler(text, chat)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("Error leyendo comandos de Telegram: %s", e)
                await asyncio.sleep(10)

    async def discover_chats(self) -> list[tuple[str, str]]:
        data = await self.call("getUpdates")
        found: dict[str, str] = {}
        for upd in data.get("result", []):
            chat = (upd.get("message") or upd.get("channel_post") or {}).get("chat") or {}
            if chat:
                name = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
                found[str(chat["id"])] = name
        return list(found.items())
