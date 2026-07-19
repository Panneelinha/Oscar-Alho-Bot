"""Gamificação: pontos (derivados da participação), níveis/títulos, ranking,
perfil e cargos opcionais do Discord por nível."""
from __future__ import annotations

import logging
from collections import defaultdict

import discord
from discord import app_commands
from discord.ext import commands

import embeds

log = logging.getLogger("oscar.gamificacao")

# Pontos por tipo de participação.
PESOS = {
    "curtidas": 1,
    "quero": 1,
    "rsvp": 2,
    "nota": 3,
    "indicacao": 3,
    "voto_categoria": 2,
    "voto_final": 3,
    "palpite": 2,
}
PESO_ACERTO_BOLAO = 5

ROTULOS = {
    "curtidas": "👍 Curtidas",
    "quero": "🍿 Quero assistir",
    "rsvp": "🎟️ Presenças",
    "nota": "🧄 Notas dadas",
    "indicacao": "🏆 Indicações",
    "voto_categoria": "🗳️ Votos de categoria",
    "voto_final": "🎬 Votos finais",
    "palpite": "🎰 Palpites",
}

# Níveis: (pontos mínimos, título). Em ordem crescente.
NIVEIS = [
    (0, "🎟️ Figurante"),
    (10, "🍿 Espectador"),
    (25, "🎬 Cinéfilo"),
    (50, "⭐ Crítico"),
    (100, "🏆 Jurado do Alho"),
    (200, "👑 Lenda do Alho"),
]


def nivel_de(pontos: int) -> tuple[str, int | None, str | None]:
    """Retorna (titulo_atual, pontos_para_proximo|None, titulo_proximo|None)."""
    titulo = NIVEIS[0][1]
    for thr, nome in NIVEIS:
        if pontos >= thr:
            titulo = nome
        else:
            return titulo, thr - pontos, nome
    return titulo, None, None


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (perms.manage_guild or perms.administrator))


class Gamificacao(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _pontuacao(self, include_site: bool = True) -> dict[int, dict]:
        """Calcula pontos do bot e, opcionalmente, soma os pontos ganhos no site."""
        counts = await self.bot.db.participation_counts()
        site_points: dict[int, int] = {}
        if include_site and getattr(self.bot, "supabase", None):
            try:
                site_points = await self.bot.supabase.site_points_by_discord()
            except Exception as exc:  # noqa: BLE001
                log.warning("Não foi possível carregar os pontos do site: %s", exc)
        # acertos no bolão (vencedores travados pela cédula final)
        winners: dict[str, str] = {}
        for cat in await self.bot.db.finalists_categories():
            rk = await self.bot.db.final_ranking(cat, 1)
            if rk:
                winners[cat] = rk[0][0]
        acertos: dict[int, int] = defaultdict(int)
        for uid, cat, cid in await self.bot.db.all_bets():
            if winners.get(cat) == cid:
                acertos[uid] += 1
        voz = await self.bot.db.voice_points_per_user()
        voz_secs = await self.bot.db.voice_seconds_per_user()
        out: dict[int, dict] = {}
        uids = set(counts) | set(acertos) | set(voz) | set(site_points)
        for uid in uids:
            d = counts.get(uid, {})
            pontos = sum(d.get(k, 0) * PESOS[k] for k in PESOS)
            pontos += acertos.get(uid, 0) * PESO_ACERTO_BOLAO
            pontos += voz.get(uid, 0)
            pontos += site_points.get(uid, 0)
            out[uid] = {
                "pontos": pontos,
                "breakdown": d,
                "acertos": acertos.get(uid, 0),
                "voz_pontos": voz.get(uid, 0),
                "voz_secs": voz_secs.get(uid, 0),
                "site_points": site_points.get(uid, 0),
            }
        return out

    @app_commands.command(name="ranking_pontos", description="Ranking dos membros mais participativos.")
    async def ranking_pontos(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        pont = await self._pontuacao()
        rows = sorted(
            (
                (uid, info["pontos"], nivel_de(info["pontos"])[0])
                for uid, info in pont.items()
                if info["pontos"] > 0
            ),
            key=lambda x: -x[1],
        )
        await interaction.followup.send(embed=embeds.ranking_pontos_embed(rows))

    @app_commands.command(name="perfil", description="Seus pontos, nível e participação no Oscar Alho.")
    @app_commands.describe(membro="Ver o perfil de outra pessoa (opcional)")
    async def perfil(
        self, interaction: discord.Interaction, membro: discord.Member | None = None
    ) -> None:
        await interaction.response.defer()
        alvo = membro or interaction.user
        pont = await self._pontuacao()
        info = pont.get(
            alvo.id,
            {
                "pontos": 0,
                "breakdown": {},
                "acertos": 0,
                "voz_pontos": 0,
                "voz_secs": 0,
                "site_points": 0,
            },
        )
        pontos, breakdown, acertos = info["pontos"], info["breakdown"], info["acertos"]
        titulo, falta, prox = nivel_de(pontos)

        embed = discord.Embed(title=f"Perfil — {titulo}", color=embeds.COR)
        embed.set_author(name=alvo.display_name, icon_url=alvo.display_avatar.url)
        embed.add_field(name="Pontos", value=f"**{pontos}** pts", inline=True)
        if falta is not None:
            embed.add_field(name="Próximo nível", value=f"{prox}\nfaltam **{falta}** pts", inline=True)
        else:
            embed.add_field(name="Próximo nível", value="nível máximo! 👑", inline=True)

        linhas = []
        for k, rotulo in ROTULOS.items():
            q = breakdown.get(k, 0)
            if q:
                linhas.append(f"{rotulo}: {q} (+{q * PESOS[k]})")
        if acertos:
            linhas.append(f"🎯 Acertos no bolão: {acertos} (+{acertos * PESO_ACERTO_BOLAO})")
        if info["voz_pontos"]:
            linhas.append(f"🎙️ Tempo na call: {info['voz_secs'] // 60} min (+{info['voz_pontos']})")
        if info["site_points"]:
            linhas.append(f"🌐 Participação no site: +{info['site_points']}")
        embed.add_field(
            name="Participação",
            value="\n".join(linhas) or "_Ainda sem participação. Bora começar!_",
            inline=False,
        )

        # cargo opcional do Discord (se ativado neste servidor)
        if interaction.guild and membro is None:
            await self._talvez_aplicar_cargo(interaction.guild, alvo, titulo)
        await interaction.followup.send(embed=embed)

    # ---------- cargos opcionais ----------
    def _flag_key(self, guild_id: int) -> str:
        return f"cargos_on:{guild_id}"

    async def _cargos_ativos(self, guild_id: int) -> bool:
        return (await self.bot.db.get_setting(self._flag_key(guild_id))) == "1"

    async def _talvez_aplicar_cargo(self, guild: discord.Guild, membro, titulo: str) -> None:
        if not isinstance(membro, discord.Member):
            return
        if not await self._cargos_ativos(guild.id):
            return
        if not guild.me.guild_permissions.manage_roles:
            return
        nomes_nivel = {nome for _thr, nome in NIVEIS}
        alvo = discord.utils.get(guild.roles, name=titulo)
        if alvo is None:
            return
        try:
            remover = [r for r in membro.roles if r.name in nomes_nivel and r != alvo]
            if remover:
                await membro.remove_roles(*remover, reason="Oscar Alho: nível")
            if alvo not in membro.roles:
                await membro.add_roles(alvo, reason="Oscar Alho: nível")
        except discord.DiscordException as e:
            log.warning("Falha ao aplicar cargo em %s: %s", membro, e)

    @app_commands.command(name="config_cargos", description="(admin) Liga/desliga cargos automáticos por nível neste servidor.")
    @app_commands.describe(ativar="True para ligar (cria os cargos), False para desligar")
    @app_commands.default_permissions(manage_guild=True)
    async def config_cargos(self, interaction: discord.Interaction, ativar: bool) -> None:
        if not _is_admin(interaction) or interaction.guild is None:
            await interaction.response.send_message("🔒 Apenas administradores, em um servidor.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if not ativar:
            await self.bot.db.set_setting(self._flag_key(interaction.guild.id), "0")
            await interaction.followup.send("🛑 Cargos automáticos **desligados** (os cargos existentes não foram apagados).", ephemeral=True)
            return
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.followup.send(
                "⚠️ Preciso da permissão **Gerenciar Cargos** para criar/atribuir os cargos.", ephemeral=True
            )
            return
        criados = 0
        for _thr, nome in NIVEIS:
            if discord.utils.get(interaction.guild.roles, name=nome) is None:
                try:
                    await interaction.guild.create_role(name=nome, reason="Oscar Alho: níveis")
                    criados += 1
                except discord.DiscordException as e:
                    log.warning("Falha ao criar cargo %s: %s", nome, e)
        await self.bot.db.set_setting(self._flag_key(interaction.guild.id), "1")
        await interaction.followup.send(
            f"✅ Cargos automáticos **ligados**! ({criados} cargo(s) criado(s)).\n"
            f"Os membros recebem o cargo do nível ao usar `/perfil`, ou rode `/sincronizar_cargos`.\n"
            f"_Dica: arraste o cargo do bot para cima dos cargos de nível, senão não consigo atribuí-los._",
            ephemeral=True,
        )

    @app_commands.command(name="sincronizar_cargos", description="(admin) Aplica os cargos de nível a todos que pontuaram.")
    @app_commands.default_permissions(manage_guild=True)
    async def sincronizar_cargos(self, interaction: discord.Interaction) -> None:
        if not _is_admin(interaction) or interaction.guild is None:
            await interaction.response.send_message("🔒 Apenas administradores, em um servidor.", ephemeral=True)
            return
        if not await self._cargos_ativos(interaction.guild.id):
            await interaction.response.send_message("Ative antes com `/config_cargos ativar:True`.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        pont = await self._pontuacao()
        aplicados = 0
        for uid, info in pont.items():
            pontos = info["pontos"]
            if pontos <= 0:
                continue
            membro = interaction.guild.get_member(uid)
            if membro is None:
                continue
            await self._talvez_aplicar_cargo(interaction.guild, membro, nivel_de(pontos)[0])
            aplicados += 1
        await interaction.followup.send(f"✅ Cargos aplicados a **{aplicados}** membro(s).", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Gamificacao(bot))
