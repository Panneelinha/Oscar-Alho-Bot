"""Comandos de votação: /votar, /desvotar, /ranking, /meusvotos."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import embeds


async def _film_autocomplete(interaction: discord.Interaction, current: str):
    bot = interaction.client
    try:
        filmes = (
            await bot.catalog.buscar(current, limite=25)
            if current
            else (await bot.catalog.todos())[:25]
        )
    except Exception:
        return []
    return [app_commands.Choice(name=mv.name[:100], value=mv.id) for mv in filmes[:25]]


class Votacao(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="votar", description="Vote em um filme (clique de novo para tirar o voto).")
    @app_commands.describe(filme="Escolha o filme")
    @app_commands.autocomplete(filme=_film_autocomplete)
    async def votar(self, interaction: discord.Interaction, filme: str) -> None:
        mv = await self.bot.catalog.por_id(filme)
        if mv is None:
            achados = await self.bot.catalog.buscar(filme, limite=1)
            mv = achados[0] if achados else None
        if mv is None:
            await interaction.response.send_message(
                f"Não encontrei **{filme}**.", ephemeral=True
            )
            return
        votou = await self.bot.db.toggle_vote(
            interaction.user.id, mv.id, mv.name, interaction.guild_id
        )
        total = await self.bot.db.count_votes(mv.id)
        msg = (
            f"✅ Você votou em **{mv.name}**! Total: {total} voto(s)."
            if votou
            else f"↩️ Voto removido de **{mv.name}**. Total: {total} voto(s)."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="ranking", description="Filmes mais votados pelos membros.")
    async def ranking(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        rows = await self.bot.db.ranking(limit=10)
        await interaction.followup.send(embed=embeds.ranking_embed(rows))

    @app_commands.command(name="meusvotos", description="Veja em quais filmes você votou.")
    async def meusvotos(self, interaction: discord.Interaction) -> None:
        cur = await self.bot.db.db.execute(
            "SELECT card_name FROM votes WHERE user_id=? ORDER BY created_at DESC",
            (interaction.user.id,),
        )
        nomes = [r[0] for r in await cur.fetchall()]
        if not nomes:
            await interaction.response.send_message(
                "Você ainda não votou em nenhum filme. Use `/votar`.", ephemeral=True
            )
            return
        texto = "\n".join(f"• {n}" for n in nomes)
        await interaction.response.send_message(
            f"**Seus votos ({len(nomes)}):**\n{texto}", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Votacao(bot))
