"""Pontos por tempo na call do cinema, contados apenas durante a sessão.

Conta o tempo em que o membro está no canal de voz configurado ("cinema") E
dentro do horário de uma sessão agendada no Trello. +1 ponto a cada 15 min
(teto 6 por sessão), somado pela gamificação.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

log = logging.getLogger("oscar.voz")

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # pragma: no cover
    TZ = timezone.utc

DUR_SESSAO_H = 4  # janela considerada "durante a sessão"


def overlap_por_sessao(
    inicio: datetime, fim: datetime, sessoes: list[tuple[str, datetime]]
) -> list[tuple[str, int]]:
    """Quantos segundos de [inicio, fim] caem dentro de cada janela de sessão.
    sessoes = [(chave, dt_inicio_naive_SP), ...]. Retorna [(chave, segundos)]."""
    out = []
    for chave, dt in sessoes:
        ini = max(inicio, dt)
        fimj = min(fim, dt + timedelta(hours=DUR_SESSAO_H))
        secs = int((fimj - ini).total_seconds())
        if secs > 0:
            out.append((chave, secs))
    return out


def _agora() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


class Voz(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # (guild_id, user_id) -> momento desde o qual ainda não contabilizamos
        self._desde: dict[tuple[int, int], datetime] = {}

    async def cog_load(self) -> None:
        self.flush_periodico.start()

    async def cog_unload(self) -> None:
        self.flush_periodico.cancel()

    def _cinema_key(self, guild_id: int) -> str:
        return f"cinema:{guild_id}"

    async def _cinema_id(self, guild_id: int) -> int | None:
        v = await self.bot.db.get_setting(self._cinema_key(guild_id))
        return int(v) if v and v.isdigit() else None

    async def _sessoes_dt(self) -> list[tuple[str, datetime]]:
        try:
            sessoes = await self.bot.catalog.sessoes()
        except Exception:  # noqa: BLE001
            return []
        return [(s.chave, s.dt) for s in sessoes if s.dt and s.chave]

    async def _contabilizar(self, guild_id: int, user_id: int, fim: datetime) -> None:
        """Soma o tempo desde a última marcação até `fim`, só o que cair em sessão."""
        key = (guild_id, user_id)
        inicio = self._desde.get(key)
        if inicio is None or fim <= inicio:
            return
        for chave, secs in overlap_por_sessao(inicio, fim, await self._sessoes_dt()):
            await self.bot.db.add_voice_seconds(user_id, chave, guild_id, secs)
        self._desde[key] = fim

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return
        cinema = await self._cinema_id(member.guild.id)
        if cinema is None:
            return
        antes = before.channel and before.channel.id == cinema
        agora = after.channel and after.channel.id == cinema
        key = (member.guild.id, member.id)
        if agora and not antes:
            self._desde[key] = _agora()  # entrou no cinema
        elif antes and not agora:
            await self._contabilizar(member.guild.id, member.id, _agora())  # saiu
            self._desde.pop(key, None)

    @tasks.loop(minutes=5)
    async def flush_periodico(self) -> None:
        if self.bot.is_closed():
            return
        agora = _agora()
        for (gid, uid) in list(self._desde):
            await self._contabilizar(gid, uid, agora)

    @flush_periodico.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()
        # "fotografa" quem já está no cinema ao subir (não perde quem já estava)
        for guild in self.bot.guilds:
            cinema = await self._cinema_id(guild.id)
            if cinema is None:
                continue
            canal = guild.get_channel(cinema)
            if isinstance(canal, discord.VoiceChannel):
                for m in canal.members:
                    if not m.bot:
                        self._desde.setdefault((guild.id, m.id), _agora())

    @app_commands.command(name="config_cinema", description="(admin) Define o canal de voz do cinema (pontos por tempo na sessão).")
    @app_commands.describe(canal="Canal de voz do cinema (em branco para desligar)")
    @app_commands.default_permissions(manage_guild=True)
    async def config_cinema(
        self, interaction: discord.Interaction, canal: discord.VoiceChannel | None = None
    ) -> None:
        perms = getattr(interaction.user, "guild_permissions", None)
        if not (perms and (perms.manage_guild or perms.administrator)) or interaction.guild is None:
            await interaction.response.send_message("🔒 Apenas administradores, em um servidor.", ephemeral=True)
            return
        if canal is None:
            await self.bot.db.set_setting(self._cinema_key(interaction.guild.id), "")
            await interaction.response.send_message("🛑 Canal do cinema removido (sem pontos por call).", ephemeral=True)
            return
        await self.bot.db.set_setting(self._cinema_key(interaction.guild.id), str(canal.id))
        await interaction.response.send_message(
            f"🎬 Cinema definido: {canal.mention}.\n"
            "Quem ficar nesse canal **durante a sessão** ganha pontos (+1 a cada 15 min, até 6).",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Voz(bot))
