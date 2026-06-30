"""Cerimônia do Oscar Alho — fluxo em fases:
indicações (público) → /abrir_votacao (admin trava finalistas) →
/votar_final (cédula entre finalistas) → /cerimonia (revela vencedores)."""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

import embeds
from movies import CATEGORIAS_PREMIACAO

log = logging.getLogger("oscar.cerimonia")

FASE = "fase"
F_INDICACOES = "indicacoes"
F_VOTACAO = "votacao"
F_ENCERRADA = "encerrada"
EDICAO = "Oscar Alho"


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (perms.manage_guild or perms.administrator))


class _FinalSelect(discord.ui.Select):
    def __init__(self, categoria: str, finalistas: list[tuple[str, str, int]], atual: str | None):
        self.categoria = categoria
        self._nomes = {cid: nome for cid, nome, _c in finalistas}
        options = [
            discord.SelectOption(
                label=nome[:100], value=cid, description=f"{c} indicações",
                default=(cid == atual),
            )
            for cid, nome, c in finalistas[:25]
        ]
        super().__init__(
            placeholder=f"Vote no vencedor de «{categoria}»…",
            min_values=1, max_values=1, options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        cid = self.values[0]
        nome = self._nomes.get(cid, "(filme)")
        await interaction.client.db.set_final_vote(  # type: ignore[attr-defined]
            interaction.user.id, self.categoria, cid, nome, interaction.guild_id
        )
        await interaction.response.send_message(
            f"🗳️ Voto final secreto registrado: **{nome}** para **{self.categoria}**!\n"
            "Pode trocar rodando o comando de novo.",
            ephemeral=True,
        )


class _FinalView(discord.ui.View):
    def __init__(self, categoria, finalistas, atual):
        super().__init__(timeout=300)
        self.add_item(_FinalSelect(categoria, finalistas, atual))


class _PalpiteSelect(discord.ui.Select):
    def __init__(self, categoria: str, finalistas: list[tuple[str, str, int]], atual: str | None):
        self.categoria = categoria
        self._nomes = {cid: nome for cid, nome, _c in finalistas}
        options = [
            discord.SelectOption(label=nome[:100], value=cid, default=(cid == atual))
            for cid, nome, _c in finalistas[:25]
        ]
        super().__init__(
            placeholder=f"Quem VENCE «{categoria}»?", min_values=1, max_values=1, options=options
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        cid = self.values[0]
        nome = self._nomes.get(cid, "(filme)")
        await interaction.client.db.set_bet(  # type: ignore[attr-defined]
            interaction.user.id, self.categoria, cid, nome, interaction.guild_id
        )
        await interaction.response.send_message(
            f"🎰 Palpite registrado: você apostou em **{nome}** para **{self.categoria}**!",
            ephemeral=True,
        )


class _PalpiteView(discord.ui.View):
    def __init__(self, categoria, finalistas, atual):
        super().__init__(timeout=300)
        self.add_item(_PalpiteSelect(categoria, finalistas, atual))


class Cerimonia(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _broadcast(self, interaction: discord.Interaction, embed: discord.Embed) -> int:
        targets = await self.bot.announce_targets()
        n = 0
        for _gid, canal in targets:
            try:
                await canal.send(embed=embed)
                n += 1
            except discord.DiscordException:
                pass
        if n == 0 and interaction.channel is not None:
            try:
                await interaction.channel.send(embed=embed)
            except discord.DiscordException:
                pass
        return n

    async def _cat_autocomplete(self, interaction: discord.Interaction, current: str):
        cats = await self.bot.db.finalists_categories()
        cur = current.lower()
        return [
            app_commands.Choice(name=c[:100], value=c) for c in cats if cur in c.lower()
        ][:25]

    async def _winners_map(self) -> dict[str, str]:
        winners: dict[str, str] = {}
        for cat in await self.bot.db.finalists_categories():
            rk = await self.bot.db.final_ranking(cat, 1)
            if rk:
                winners[cat] = rk[0][0]
        return winners

    async def _bolao_ranking(self) -> tuple[list[tuple[int, int, int]], int]:
        from collections import defaultdict

        winners = await self._winners_map()
        acertos: dict[int, int] = defaultdict(int)
        total: dict[int, int] = defaultdict(int)
        for uid, cat, cid in await self.bot.db.all_bets():
            total[uid] += 1
            if winners.get(cat) == cid:
                acertos[uid] += 1
        ranking = sorted(
            ((uid, acertos[uid], total[uid]) for uid in total),
            key=lambda x: (-x[1], -x[2]),
        )
        return ranking, len(winners)

    # ---------- admin: abrir votação ----------
    @app_commands.command(name="abrir_votacao", description="(admin) Trava os finalistas e abre a votação da cerimônia.")
    @app_commands.describe(finalistas="Quantos finalistas por categoria (padrão 5)")
    @app_commands.default_permissions(manage_guild=True)
    async def abrir_votacao(
        self, interaction: discord.Interaction,
        finalistas: app_commands.Range[int, 1, 10] = 5,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message("🔒 Apenas administradores.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.clear_finalists()
        await self.bot.db.clear_final_votes()
        await self.bot.db.clear_bets()
        data = []
        for cat in CATEGORIAS_PREMIACAO:
            rows = await self.bot.db.nomination_ranking(cat, int(finalistas))
            if not rows:
                continue
            for cid, nome, c in rows:
                await self.bot.db.add_finalist(cat, cid, nome, c)
            data.append((cat, [(nome, c) for _cid, nome, c in rows]))
        if not data:
            await interaction.followup.send(
                "Ainda não há indicações suficientes. Peça ao público para usar o botão **Indicar**.",
                ephemeral=True,
            )
            return
        await self.bot.db.set_setting(FASE, F_VOTACAO)
        n = await self._broadcast(interaction, embeds.finalistas_embed(data))
        await interaction.followup.send(
            f"✅ Votação **aberta**! Finalistas travados em **{len(data)}** categoria(s) "
            f"e anunciados em **{n}** canal(is).\nO público vota com `/votar_final`.",
            ephemeral=True,
        )

    # ---------- público: votar na final ----------
    @app_commands.command(name="votar_final", description="Vote no vencedor de uma categoria (entre os finalistas).")
    @app_commands.describe(categoria="Categoria da cerimônia")
    async def votar_final(self, interaction: discord.Interaction, categoria: str) -> None:
        fase = await self.bot.db.get_setting(FASE, F_INDICACOES)
        if fase != F_VOTACAO:
            await interaction.response.send_message(
                "A votação final não está aberta agora. Aguarde o anúncio dos finalistas! 🎬",
                ephemeral=True,
            )
            return
        cats = await self.bot.db.finalists_categories()
        alvo = next((c for c in cats if c.lower() == categoria.lower()), categoria)
        finalistas = await self.bot.db.finalists_for(alvo)
        if not finalistas:
            await interaction.response.send_message(
                f"Não há finalistas em **{categoria}**.", ephemeral=True
            )
            return
        atual = await self.bot.db.user_final_vote(interaction.user.id, alvo)
        linhas = "\n".join(f"• **{nome}** ({c} indicações)" for _cid, nome, c in finalistas)
        embed = discord.Embed(
            title=f"🏆 Finalistas — {alvo}", color=embeds.COR, description=linhas
        )
        embed.set_footer(text="Seu voto é secreto. Escolha abaixo 👇")
        await interaction.response.send_message(
            embed=embed, view=_FinalView(alvo, finalistas, atual), ephemeral=True
        )

    @votar_final.autocomplete("categoria")
    async def _vf_ac(self, interaction: discord.Interaction, current: str):
        return await self._cat_autocomplete(interaction, current)

    # ---------- admin: realizar a cerimônia ----------
    @app_commands.command(name="cerimonia", description="(admin) Revela os vencedores do Oscar Alho.")
    @app_commands.default_permissions(manage_guild=True)
    async def cerimonia(self, interaction: discord.Interaction) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message("🔒 Apenas administradores.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        cats = set(await self.bot.db.finalists_categories())
        if not cats:
            await interaction.followup.send(
                "Abra a votação primeiro com `/abrir_votacao`.", ephemeral=True
            )
            return
        winners = []
        for cat in CATEGORIAS_PREMIACAO:
            if cat not in cats:
                continue
            rk = await self.bot.db.final_ranking(cat, 1)
            if rk:
                winners.append((cat, rk[0][1], rk[0][2]))
            else:
                winners.append((cat, None, 0))
        await self.bot.db.set_setting(FASE, F_ENCERRADA)
        n = await self._broadcast(interaction, embeds.vencedores_embed(winners, EDICAO))
        # apura o bolão e anuncia o ranking de palpiteiros
        ranking, ncat = await self._bolao_ranking()
        if ranking:
            await self._broadcast(
                interaction, embeds.bolao_embed(ranking, ncat, "🎰 Resultado do Bolão")
            )
        await interaction.followup.send(
            f"🏆 Cerimônia realizada! Vencedores anunciados em **{n}** canal(is)."
            + (f"\n🎰 Bolão apurado: **{len(ranking)}** palpiteiro(s)." if ranking else ""),
            ephemeral=True,
        )

    # ---------- bolão ----------
    @app_commands.command(name="palpite", description="Aposte em quem vai VENCER uma categoria (bolão).")
    @app_commands.describe(categoria="Categoria da cerimônia")
    async def palpite(self, interaction: discord.Interaction, categoria: str) -> None:
        fase = await self.bot.db.get_setting(FASE, F_INDICACOES)
        if fase != F_VOTACAO:
            await interaction.response.send_message(
                "O bolão só fica aberto durante a votação (após os finalistas). 🎰",
                ephemeral=True,
            )
            return
        cats = await self.bot.db.finalists_categories()
        alvo = next((c for c in cats if c.lower() == categoria.lower()), categoria)
        finalistas = await self.bot.db.finalists_for(alvo)
        if not finalistas:
            await interaction.response.send_message(
                f"Não há finalistas em **{categoria}**.", ephemeral=True
            )
            return
        atual = await self.bot.db.user_bet(interaction.user.id, alvo)
        linhas = "\n".join(f"• **{nome}**" for _cid, nome, _c in finalistas)
        embed = discord.Embed(
            title=f"🎰 Palpite — {alvo}", color=embeds.COR,
            description=f"Quem você acha que vai **vencer**?\n{linhas}",
        )
        embed.set_footer(text="1 ponto se cravar o vencedor 🎯")
        await interaction.response.send_message(
            embed=embed, view=_PalpiteView(alvo, finalistas, atual), ephemeral=True
        )

    @palpite.autocomplete("categoria")
    async def _palpite_ac(self, interaction: discord.Interaction, current: str):
        return await self._cat_autocomplete(interaction, current)

    @app_commands.command(name="meus_palpites", description="Veja seus palpites do bolão.")
    async def meus_palpites(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.bets_by_user(interaction.user.id)
        if not rows:
            await interaction.response.send_message(
                "Você ainda não apostou. Use `/palpite` durante a votação.", ephemeral=True
            )
            return
        texto = "\n".join(f"• **{cat}**: {nome}" for cat, nome in rows)
        await interaction.response.send_message(
            f"🎰 **Seus palpites ({len(rows)}):**\n{texto}", ephemeral=True
        )

    @app_commands.command(name="bolao_ranking", description="Ranking do bolão (palpiteiros que mais acertaram).")
    async def bolao_ranking(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        fase = await self.bot.db.get_setting(FASE, F_INDICACOES)
        if fase != F_ENCERRADA:
            n = await self.bot.db.bettors_count()
            await interaction.followup.send(
                f"🎰 O bolão ainda está rolando — **{n}** palpiteiro(s) até agora. "
                f"O ranking sai depois da `/cerimonia`."
            )
            return
        ranking, ncat = await self._bolao_ranking()
        await interaction.followup.send(embed=embeds.bolao_embed(ranking, ncat))

    # ---------- status / reset ----------
    @app_commands.command(name="cerimonia_status", description="Em que fase está a cerimônia do Oscar Alho.")
    async def cerimonia_status(self, interaction: discord.Interaction) -> None:
        fase = await self.bot.db.get_setting(FASE, F_INDICACOES)
        rotulo = {
            F_INDICACOES: "📝 **Indicações abertas** — use o botão **Indicar** ou `/indicar`.",
            F_VOTACAO: "🗳️ **Votação final aberta** — use `/votar_final <categoria>`.",
            F_ENCERRADA: "🏆 **Encerrada** — vencedores já anunciados.",
        }.get(fase, fase)
        n_fin = len(await self.bot.db.finalists_categories())
        embed = discord.Embed(title="🎬 Cerimônia do Oscar Alho", color=embeds.COR, description=rotulo)
        if n_fin:
            embed.set_footer(text=f"{n_fin} categoria(s) com finalistas")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="reabrir_indicacoes", description="(admin) Volta para a fase de indicações (zera finalistas e votos finais).")
    @app_commands.default_permissions(manage_guild=True)
    async def reabrir_indicacoes(self, interaction: discord.Interaction) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message("🔒 Apenas administradores.", ephemeral=True)
            return
        await self.bot.db.clear_finalists()
        await self.bot.db.clear_final_votes()
        await self.bot.db.clear_bets()
        await self.bot.db.set_setting(FASE, F_INDICACOES)
        await interaction.response.send_message(
            "↩️ Indicações reabertas. Finalistas, votos finais e palpites foram zerados "
            "(as indicações do público continuam).",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Cerimonia(bot))
