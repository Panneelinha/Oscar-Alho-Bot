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
from supabase_client import SupabaseSyncClient
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
    "cogs.site_sync",
]


class OscarAlhoBot(commands.Bot):
    def __init__(self, cfg: Config) -> None:
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.cfg = cfg
        self.trello = TrelloClient(cfg.trello_key, cfg.trello_token, cfg.trello_board_id)
        self.catalog = Catalog(self.trello)
        self.supabase = (
            SupabaseSyncClient(cfg.supabase_url, cfg.supabase_service_role_key)
            if cfg.supabase_url and cfg.supabase_service_role_key
            else None
        )
        self.db = Database(cfg.db_path)
        self.telegram = None   # ponte opcional (telegram_bridge.TelegramBridge)
        self.kick = None       # cliente opcional da Kick (kick_client.KickClient)
        self.kick_chat = None  # leitor de chat da Kick (kick_chat.KickChatListener)

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
                    self.cfg.kick_channel_slug,
                )
                await self.telegram.start()
            except Exception as e:  # noqa: BLE001
                log.warning("Ponte Telegram desativada: %s", e)
                self.telegram = None

        if self.cfg.kick_client_id and self.cfg.kick_client_secret and self.cfg.kick_channel_slug:
            try:
                from kick_client import KickClient

                self.kick = KickClient(
                    self.cfg.kick_client_id,
                    self.cfg.kick_client_secret,
                    self.cfg.kick_channel_slug,
                    self.cfg.kick_refresh_token,
                    self.db,
                )
                if await self.kick._ensure():
                    log.info("Cliente Kick pronto (canal %s).", self.cfg.kick_channel_slug)
                else:
                    log.warning("Kick: não consegui obter token (refresh inválido?).")
            except Exception as e:  # noqa: BLE001
                log.warning("Cliente Kick desativado: %s", e)
                self.kick = None

        if self.kick is not None and not self.cfg.kick_chatroom_id:
            log.warning("Kick: KICK_CHATROOM_ID não definido — leitor de chat DESLIGADO.")
        if self.kick is not None and self.cfg.kick_chatroom_id:
            try:
                from kick_chat import KickChatListener

                self.kick_chat = KickChatListener(self, self.cfg.kick_chatroom_id)
                self.kick_chat.start()
                log.info("Leitor do chat da Kick iniciado (chatroom %s).", self.cfg.kick_chatroom_id)
            except Exception as e:  # noqa: BLE001
                log.warning("Leitor da Kick desativado: %s", e)
                self.kick_chat = None

    async def notify_telegram(self, texto: str, foto: bytes | None = None) -> None:
        """Espelha um anúncio no Telegram, se a ponte estiver ativa."""
        if self.telegram is not None:
            await self.telegram.anunciar(texto, foto)

    async def notify_kick(self, texto: str) -> None:
        """Posta um anúncio no chat da Kick, se o cliente estiver ativo."""
        if self.kick is not None:
            try:
                await self.kick.enviar(texto)
            except Exception as e:  # noqa: BLE001
                log.warning("Falha ao postar na Kick: %s", e)

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
        if self.kick_chat is not None:
            await self.kick_chat.stop()
        if self.telegram is not None:
            await self.telegram.stop()
        if self.kick is not None:
            await self.kick.close()
        await super().close()
        await self.trello.close()
        if self.supabase is not None:
            await self.supabase.close()
        await self.db.close()


def main() -> None:
    cfg = Config.from_env()
    bot = OscarAlhoBot(cfg)
    bot.run(cfg.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
