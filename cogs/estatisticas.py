"""Estatísticas do clube: /estatisticas (catálogo do Trello + atividade no Discord)."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import embeds


class Estatisticas(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="estatisticas", description="Panorama do clube: catálogo + participação.")
    async def estatisticas(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        db = self.bot.db
        cat = await self.bot.catalog.estatisticas()

        participacao = await db.participation_counts()
        nota_clube, n_aval = await db.overall_rating()
        top_curtido = await db.ranking(1)
        top_indicado = await db.top_nominated(1)
        top_nota = await db.ratings_ranking(1)
        clube = {
            "membros": len(participacao),
            "participacoes": sum(sum(d.values()) for d in participacao.values()),
            "nota_clube": nota_clube,
            "n_avaliacoes": n_aval,
            "top_curtido": (top_curtido[0][1], top_curtido[0][2]) if top_curtido else None,
            "top_indicado": top_indicado[0] if top_indicado else None,
            "top_nota": (top_nota[0][1], top_nota[0][2]) if top_nota else None,
        }
        await interaction.followup.send(embed=embeds.estatisticas_embed(cat, clube))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Estatisticas(bot))
