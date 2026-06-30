"""Bot do Discord do Oscar Alho 🧄🎬

Lê os filmes do board do Trello e oferece comandos de programação, ficha,
catálogo, indicados e votação. Rode com:  python bot.py
"""
from __future__ import annotations

import logging

import discord
from discord.ext import commands

from catalog import Catalog
from config import Config
from db import Database
from trello_client import TrelloClient
from ui import InteragirButton, RSVPButton

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("oscar")
# Evita vazar o token do Telegram nos logs (httpx loga a URL com o token).
logging.getLogger("httpx").setLevel(logging.WARNING)

COGS = [
    "cogs.ajuda",
    "cogs.filmes",
    "cogs.votacao",
    "cogs.categorias",
    "cogs.indicacoes",
    "cogs.sessoes",
    "cogs.cerimonia",
    "cogs.gamificacao",
    "cogs.voz",
    "cogs.estatisticas",
    "cogs.admin",
    "cogs.anuncios",
    "cogs.trello_sync",
]


class OscarAlhoBot(commands.Bot):
    def __init__(self, cfg: Config) -> None:
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.cfg = cfg
        self.trello = TrelloClient(cfg.trello_key, cfg.trello_token, cfg.trello_board_id)
        self.catalog = Catalog(self.trello)
        self.db = Database(cfg.db_path)
        self.telegram = None  # ponte opcional (telegram_bridge.TelegramBridge)

    async def setup_hook(self) -> None:
        await self.db.connect()
        self.add_dynamic_items(InteragirButton, RSVPButton)  # botões persistentes
        for ext in COGS:
            await self.load_extension(ext)

        if self.cfg.guild_id:
            guild = discord.Object(id=self.cfg.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Comandos sincronizados no servidor %s.", self.cfg.guild_id)
        else:
            await self.tree.sync()
            log.info("Comandos sincronizados globalmente (pode levar até 1h).")

        if self.cfg.telegram_token:
            try:
                from telegram_bridge import TelegramBridge

                self.telegram = TelegramBridge(
                    self.cfg.telegram_token,
                    self.cfg.telegram_allowed_ids,
                    self.cfg.telegram_chat_id,
                    self.catalog,
                    self.db,
                    self.trello,
                )
                await self.telegram.start()
            except Exception as e:  # noqa: BLE001
                log.warning("Ponte Telegram desativada: %s", e)
                self.telegram = None

    async def notify_telegram(self, texto: str, foto: bytes | None = None) -> None:
        """Espelha um anúncio no Telegram, se a ponte estiver ativa."""
        if self.telegram is not None:
            await self.telegram.anunciar(texto, foto)

    async def announce_targets(self) -> list[tuple[int, "discord.abc.Messageable"]]:
        """Canais onde postar anúncios/lembretes: (guild_id, canal).
        Combina o canal do .env (legado) com os configurados por servidor."""
        alvos: dict[int, object] = {}
        if self.cfg.announce_channel_id:
            ch = self.get_channel(self.cfg.announce_channel_id)
            if ch is not None:
                alvos[getattr(ch.guild, "id", 0)] = ch
        for gid, cid in await self.db.all_announce_channels():
            ch = self.get_channel(cid)
            if ch is not None:
                alvos[gid] = ch
        return list(alvos.items())

    async def on_ready(self) -> None:
        log.info("Conectado como %s (id=%s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="os filmes do Oscar Alho 🧄"
            )
        )

    async def close(self) -> None:
        # encerra o gateway e as tarefas/cogs primeiro, depois os recursos
        if self.telegram is not None:
            await self.telegram.stop()
        await super().close()
        await self.trello.close()
        await self.db.close()


def main() -> None:
    cfg = Config.from_env()
    bot = OscarAlhoBot(cfg)
    bot.run(cfg.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
