"""Comandos de consulta: /programacao, /filme, /catalogo, /indicados."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import embeds
from media import poster_attachment
from movies import Movie


async def _film_autocomplete(interaction: discord.Interaction, current: str):
    bot = interaction.client
    try:
        filmes = await bot.catalog.buscar(current, limite=25) if current else (
            await bot.catalog.todos()
        )[:25]
    except Exception:
        return []
    return [
        app_commands.Choice(name=mv.name[:100], value=mv.id) for mv in filmes[:25]
    ]


class Filmes(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="programacao", description="Veja o que está disponível e o que vem por aí.")
    async def programacao(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        sessoes, disponivel, em_breve = await self.bot.catalog.programacao()
        await interaction.followup.send(
            embed=embeds.programacao_embed(sessoes, disponivel, em_breve)
        )

    @app_commands.command(name="filme", description="Ficha completa de um filme (nota, streaming, pôster).")
    @app_commands.describe(filme="Comece a digitar o nome do filme")
    @app_commands.autocomplete(filme=_film_autocomplete)
    async def filme(self, interaction: discord.Interaction, filme: str) -> None:
        await interaction.response.defer()
        mv = await self.bot.catalog.por_id(filme)
        if mv is None:  # usuário digitou texto livre em vez de escolher
            achados = await self.bot.catalog.buscar(filme, limite=1)
            mv = achados[0] if achados else None
        if mv is None:
            await interaction.followup.send(
                f"Não encontrei nenhum filme com **{filme}**. Tente outro nome.",
                ephemeral=True,
            )
            return
        file, poster_url = await poster_attachment(self.bot.trello, mv)
        votos = await self.bot.db.count_votes(mv.id)
        extras = await self.bot.catalog.extras(mv.id)
        nota_clube = await self.bot.db.average_rating(mv.id)
        from ui import vote_view

        kwargs = {
            "embed": embeds.movie_embed(mv, poster_url, votos, extras, nota_clube),
            "view": vote_view(mv),
        }
        if file:
            kwargs["file"] = file
        await interaction.followup.send(**kwargs)

    @app_commands.command(name="catalogo", description="Liste as categorias ou os filmes de uma categoria.")
    @app_commands.describe(categoria="Nome da lista/categoria (opcional)")
    async def catalogo(self, interaction: discord.Interaction, categoria: str | None = None) -> None:
        await interaction.response.defer()
        if not categoria:
            nomes = await self.bot.catalog.nomes_listas()
            embed = discord.Embed(
                title="📚 Categorias do Oscar Alho",
                color=embeds.COR,
                description="\n".join(f"• {n}" for n in nomes),
            )
            embed.set_footer(text="Use /catalogo <categoria> para ver os filmes")
            await interaction.followup.send(embed=embed)
            return
        movies = await self.bot.catalog.categoria(categoria)
        nome_real = movies[0].list_name if movies else categoria
        await interaction.followup.send(embed=embeds.categoria_embed(nome_real, movies))

    @catalogo.autocomplete("categoria")
    async def _cat_autocomplete(self, interaction: discord.Interaction, current: str):
        nomes = await self.bot.catalog.nomes_listas()
        cur = current.lower()
        return [
            app_commands.Choice(name=n[:100], value=n)
            for n in nomes
            if cur in n.lower()
        ][:25]

    @app_commands.command(name="indicados", description="Indicados de uma categoria de premiação.")
    @app_commands.describe(categoria="Categoria do Oscar Alho")
    async def indicados(self, interaction: discord.Interaction, categoria: str) -> None:
        await interaction.response.defer()
        movies = await self.bot.catalog.categoria(categoria)
        nome_real = movies[0].list_name if movies else categoria
        await interaction.followup.send(embed=embeds.categoria_embed(f"Indicados · {nome_real}", movies))

    @indicados.autocomplete("categoria")
    async def _ind_autocomplete(self, interaction: discord.Interaction, current: str):
        cats = await self.bot.catalog.categorias_premiacao()
        cur = current.lower()
        return [
            app_commands.Choice(name=c[:100], value=c)
            for c in cats
            if cur in c.lower()
        ][:25]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Filmes(bot))
