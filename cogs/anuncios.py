"""Anúncios: comando manual /anunciar e tarefa automática que avisa, em cada
servidor configurado, quando um filme entra em 'STREAMING - DISPONÍVEL'."""
from __future__ import annotations

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

import embeds
from movies import Movie
from ui import vote_view

log = logging.getLogger("oscar.anuncios")
EVENT_DISPONIVEL = "disponivel"


def _build_file(poster: tuple[bytes, str] | None):
    if not poster:
        return None, None
    data, nome = poster
    return discord.File(io.BytesIO(data), filename=nome), f"attachment://{nome}"


class Anuncios(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.checar_novidades.change_interval(minutes=bot.cfg.poll_minutes)

    async def cog_load(self) -> None:
        self.checar_novidades.start()

    async def cog_unload(self) -> None:
        self.checar_novidades.cancel()

    @tasks.loop(minutes=30)
    async def checar_novidades(self) -> None:
        if self.bot.is_closed():
            return
        targets = await self.bot.announce_targets()
        if not targets:
            return
        _sessoes, disponivel, _em_breve = await self.bot.catalog.programacao()

        # baseline por servidor: na 1ª vez só marca (não despeja tudo no canal).
        baseline = {
            gid: (await self.bot.db.announced_count(EVENT_DISPONIVEL, gid) == 0)
            for gid, _canal in targets
        }
        for mv in disponivel:
            midia = None  # (extras, poster) calculados só se for anunciar de fato
            for gid, canal in targets:
                if await self.bot.db.already_announced(mv.id, EVENT_DISPONIVEL, gid):
                    continue
                if baseline[gid]:
                    await self.bot.db.mark_announced(mv.id, EVENT_DISPONIVEL, gid)
                    continue
                if midia is None:
                    extras = await self.bot.catalog.extras(mv.id)
                    poster = await self.bot.trello.get_poster(mv.id) if mv.tem_poster else None
                    midia = (extras, poster)
                extras, poster = midia
                file, poster_url = _build_file(poster)
                try:
                    await canal.send(
                        embed=embeds.announce_embed(mv, poster_url, extras),
                        view=vote_view(mv),
                        file=file or discord.utils.MISSING,
                    )
                    await self.bot.db.mark_announced(mv.id, EVENT_DISPONIVEL, gid)
                except discord.DiscordException as e:
                    log.warning("Falha ao anunciar %s no guild %s: %s", mv.name, gid, e)
        for gid, _c in targets:
            if baseline[gid]:
                log.info("Linha de base criada no guild %s (%d filmes).", gid, len(disponivel))

    @checar_novidades.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(name="anunciar", description="(admin) Anuncia um filme no canal de anúncios.")
    @app_commands.describe(filme="Filme a anunciar")
    @app_commands.default_permissions(manage_messages=True)
    async def anunciar(self, interaction: discord.Interaction, filme: str) -> None:
        await interaction.response.defer(ephemeral=True)
        mv = await self.bot.catalog.por_id(filme)
        if mv is None:
            achados = await self.bot.catalog.buscar(filme, limite=1)
            mv = achados[0] if achados else None
        if mv is None:
            await interaction.followup.send(f"Não encontrei **{filme}**.", ephemeral=True)
            return
        canal = None
        if interaction.guild_id:
            cid = await self.bot.db.get_announce_channel(interaction.guild_id)
            if cid:
                canal = self.bot.get_channel(cid)
        if canal is None and self.bot.cfg.announce_channel_id:
            canal = self.bot.get_channel(self.bot.cfg.announce_channel_id)
        if canal is None:
            canal = interaction.channel
        extras = await self.bot.catalog.extras(mv.id)
        poster = await self.bot.trello.get_poster(mv.id) if mv.tem_poster else None
        file, poster_url = _build_file(poster)
        await canal.send(
            embed=embeds.announce_embed(mv, poster_url, extras),
            view=vote_view(mv),
            file=file or discord.utils.MISSING,
        )
        await interaction.followup.send(
            f"📣 Anunciado **{mv.name}** em {canal.mention}.", ephemeral=True
        )

    @anunciar.autocomplete("filme")
    async def _ac(self, interaction: discord.Interaction, current: str):
        filmes = (
            await self.bot.catalog.buscar(current, limite=25)
            if current
            else (await self.bot.catalog.todos())[:25]
        )
        return [app_commands.Choice(name=m.name[:100], value=m.id) for m in filmes[:25]]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Anuncios(bot))
