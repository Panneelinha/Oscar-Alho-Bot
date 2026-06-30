"""Votação por categoria (cédula secreta): /votar_categoria, /ranking_categoria,
/apuracao. Cada membro escolhe UM indicado por categoria; o voto é privado."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import embeds
from movies import CATEGORIAS_PREMIACAO, LISTA_FORA_PREMIACAO, Movie


async def _cat_autocomplete(interaction: discord.Interaction, current: str):
    cats = await interaction.client.catalog.categorias_premiacao()  # type: ignore[attr-defined]
    cur = current.lower()
    return [
        app_commands.Choice(name=c[:100], value=c) for c in cats if cur in c.lower()
    ][:25]


class _BallotSelect(discord.ui.Select):
    def __init__(self, categoria: str, indicados: list[Movie], voto_atual: str | None) -> None:
        options = []
        for mv in indicados[:25]:
            desc = mv.imdb_nota and f"IMDb {mv.imdb_nota}"
            options.append(
                discord.SelectOption(
                    label=mv.name[:100],
                    value=mv.id,
                    description=(desc or None),
                    default=(mv.id == voto_atual),
                )
            )
        super().__init__(
            placeholder=f"Escolha seu voto em «{categoria}»",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.categoria = categoria
        self._nomes = {mv.id: mv.name for mv in indicados}

    async def callback(self, interaction: discord.Interaction) -> None:
        card_id = self.values[0]
        nome = self._nomes.get(card_id, "(filme)")
        await interaction.client.db.set_category_vote(  # type: ignore[attr-defined]
            interaction.user.id, self.categoria, card_id, nome, interaction.guild_id
        )
        await interaction.response.send_message(
            f"🗳️ Voto secreto registrado: **{nome}** em **{self.categoria}**.\n"
            "Você pode trocar a qualquer momento rodando o comando de novo.",
            ephemeral=True,
        )


class _BallotView(discord.ui.View):
    def __init__(self, categoria: str, indicados: list[Movie], voto_atual: str | None) -> None:
        super().__init__(timeout=300)
        self.add_item(_BallotSelect(categoria, indicados, voto_atual))


class Categorias(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="votar_categoria",
        description="Vote no seu indicado favorito de uma categoria (voto secreto).",
    )
    @app_commands.describe(categoria="Categoria do Oscar Alho")
    @app_commands.autocomplete(categoria=_cat_autocomplete)
    async def votar_categoria(self, interaction: discord.Interaction, categoria: str) -> None:
        await interaction.response.defer(ephemeral=True)
        indicados = await self.bot.catalog.categoria(categoria)
        if not indicados:
            await interaction.followup.send(
                f"Não encontrei indicados em **{categoria}**.", ephemeral=True
            )
            return
        nome_real = indicados[0].list_name
        atual = await self.bot.db.user_category_vote(interaction.user.id, nome_real)
        embed = embeds.categoria_embed(f"Indicados · {nome_real}", indicados)
        embed.set_footer(text="Selecione abaixo. Seu voto é secreto e só você vê esta mensagem.")
        await interaction.followup.send(
            embed=embed, view=_BallotView(nome_real, indicados, atual), ephemeral=True
        )

    @app_commands.command(
        name="ranking_categoria",
        description="Veja a apuração (só números) de uma categoria.",
    )
    @app_commands.describe(categoria="Categoria do Oscar Alho")
    @app_commands.autocomplete(categoria=_cat_autocomplete)
    async def ranking_categoria(self, interaction: discord.Interaction, categoria: str) -> None:
        await interaction.response.defer()
        indicados = await self.bot.catalog.categoria(categoria)
        nome_real = indicados[0].list_name if indicados else categoria
        rows = await self.bot.db.category_ranking(nome_real)
        total = sum(c for *_x, c in rows)
        await interaction.followup.send(
            embed=embeds.category_ranking_embed(nome_real, rows, total)
        )

    @app_commands.command(name="apuracao", description="Apuração geral: cédula secreta × indicações do público.")
    async def apuracao(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        db = self.bot.db
        com_cedula = set(await db.categories_with_votes())
        com_indic = set(await db.categories_with_nominations())
        itens = []
        for cat in CATEGORIAS_PREMIACAO:
            if cat not in com_cedula and cat not in com_indic:
                continue
            cedula = await db.category_ranking(cat, limit=1)
            indic = await db.nomination_ranking(cat, limit=1)
            bn, bc = (cedula[0][1], cedula[0][2]) if cedula else (None, 0)
            nn, nc = (indic[0][1], indic[0][2]) if indic else (None, 0)
            itens.append((cat, (bn, bc), (nn, nc)))
        fora_rows = await db.nomination_ranking(LISTA_FORA_PREMIACAO, limit=1)
        fora = (fora_rows[0][1], fora_rows[0][2]) if fora_rows else (None, 0)
        await interaction.followup.send(embed=embeds.apuracao_geral_embed(itens, fora))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Categorias(bot))
