"""Leitor do chat da Kick (websocket do Pusher) com comandos.

Conexão anônima de saída (não precisa de webhook/URL pública). Lê as mensagens
do chat, reconhece comandos com `!` e responde via a API oficial (chat:write,
através de bot.kick). Reconecta sozinho se a conexão cair.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import aiohttp

log = logging.getLogger("oscar.kickchat")

PUSHER_KEY = "32cbd69e4b950bf97679"  # chave pública do Pusher usada pela Kick
WS_URL = (
    f"wss://ws-us2.pusher.com/app/{PUSHER_KEY}"
    "?protocol=7&client=js&version=8.4.0&flash=false"
)
COOLDOWN = 3  # segundos mínimos entre respostas (evita flood/limites)


class KickChatListener:
    def __init__(self, bot, chatroom_id: int) -> None:
        self.bot = bot
        self.chatroom_id = chatroom_id
        self._task: asyncio.Task | None = None
        self._stop = False
        self._last = 0.0

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        await self.bot.wait_until_ready()
        backoff = 5
        while not self._stop:
            try:
                await self._connect()
                backoff = 5
            except asyncio.CancelledError:
                return
            except Exception as e:  # noqa: BLE001
                log.warning("Kick chat caiu (%s); reconectando em %ss", e, backoff)
            if self._stop:
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def _connect(self) -> None:
        async with aiohttp.ClientSession() as s:
            async with s.ws_connect(WS_URL, heartbeat=25) as ws:
                async for msg in ws:
                    if self._stop:
                        break
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    try:
                        data = json.loads(msg.data)
                    except ValueError:
                        continue
                    ev = data.get("event", "")
                    if ev == "pusher:connection_established":
                        await ws.send_json(
                            {
                                "event": "pusher:subscribe",
                                "data": {"auth": "", "channel": f"chatrooms.{self.chatroom_id}.v2"},
                            }
                        )
                        log.info("Kick chat: inscrito no chatroom %s.", self.chatroom_id)
                    elif ev.endswith("ChatMessageEvent"):
                        try:
                            d = json.loads(data["data"])
                        except (ValueError, KeyError):
                            continue
                        await self._handle(
                            d.get("content", ""),
                            (d.get("sender") or {}).get("username", ""),
                        )

    async def _handle(self, content: str, username: str) -> None:
        c = (content or "").strip()
        if not c.startswith("!"):
            return
        if time.time() - self._last < COOLDOWN:
            return
        partes = c[1:].split(maxsplit=1)
        cmd = partes[0].lower()
        arg = partes[1].strip() if len(partes) > 1 else ""
        resp = await self._resposta(cmd, arg)
        if resp and self.bot.kick is not None:
            self._last = time.time()
            await self.bot.kick.enviar(resp[:480])

    async def _resposta(self, cmd: str, arg: str) -> str | None:
        cat = self.bot.catalog
        if cmd in ("ajuda", "comandos", "help"):
            return "Comandos do Oscar Alho: !programacao · !proxima · !filme <nome> · !nota <nome>"
        if cmd in ("programacao", "programação", "prog"):
            sessoes, disp, _breve = await cat.programacao()
            if sessoes:
                s = sessoes[0]
                return f"🎬 Próxima sessão: {s.titulo} ({s.quando}). E {len(disp)} filmes no streaming!"
            return f"Sem sessão agendada agora. {len(disp)} filmes disponíveis no streaming."
        if cmd in ("proxima", "próxima", "next"):
            s = await cat.proxima_sessao()
            return f"🎬 Próxima sessão: {s.titulo} — {s.quando}" if s else "Sem sessão agendada por enquanto."
        if cmd in ("filme", "ficha"):
            if not arg:
                return "Use assim: !filme <nome do filme>"
            achados = await cat.buscar(arg, limite=1)
            if not achados:
                return f"Não achei nenhum filme com '{arg}'."
            mv = achados[0]
            partes = [mv.name]
            if mv.imdb_nota:
                partes.append(f"IMDb {mv.imdb_nota}")
            if mv.duracao:
                partes.append(mv.duracao)
            if mv.streaming:
                partes.append(mv.streaming)
            return "🍿 " + " · ".join(partes)
        if cmd in ("nota", "notas"):
            if arg:
                achados = await cat.buscar(arg, limite=1)
                if achados:
                    media, n = await self.bot.db.average_rating(achados[0].id)
                    if n:
                        return f"🧄 {achados[0].name}: nota do clube {media}/10 ({n} voto(s))"
                    return f"{achados[0].name} ainda não tem nota do clube."
            rows = await self.bot.db.ratings_ranking(limit=3)
            if rows:
                top = " · ".join(f"{nome} {media}/10" for _c, nome, media, _n in rows)
                return f"🧄 Mais bem avaliados: {top}"
            return "Ainda não há notas do clube."
        return None  # comando desconhecido: ignora em silêncio
