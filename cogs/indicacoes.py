"""Comandos de interação do público:
/indicar, /quero_assistir, /ranking_quero_assistir, /minhas_indicacoes."""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

import embeds
from movies import LISTA_FORA_PREMIACAO, OPCOES_INDICACAO, foi_assistido
from ui import abrir_indicacao, registrar_quero_assistir

log = logging.getLogger("oscar.indicacoes")


def _rotulo_opcao(c: str) -> str:
    return "🚫 Fora da premiação" if c == LISTA_FORA_PREMIACAO else c


async def _opcao_autocomplete(interaction: discord.Interaction, current: str):
    cur = current.lower()
    return [
        app_commands.Choice(name=_rotulo_opcao(c)[:100], value=c)
        for c in OPCOES_INDICACAO
        if cur in c.lower() or cur in _rotulo_opcao(c).lower()
    ][:25]


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


class Indicacoes(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _resolver(self, filme: str):
        mv = await self.bot.catalog.por_id(filme)
        if mv is None:
            achados = await self.bot.catalog.buscar(filme, limite=1)
            mv = achados[0] if achados else None
        return mv

    @app_commands.command(name="indicar", description="Indique um filme já assistido a uma categoria do Oscar Alho.")
    @app_commands.describe(filme="Filme que você quer indicar")
    @app_commands.autocomplete(filme=_film_autocomplete)
    async def indicar(self, interaction: discord.Interaction, filme: str) -> None:
        mv = await self._resolver(filme)
        if mv is None:
            await interaction.response.send_message(f"Não encontrei **{filme}**.", ephemeral=True)
            return
        if not foi_assistido(mv.list_name):
            await registrar_quero_assistir(interaction, mv)
            return
        await abrir_indicacao(interaction, mv)

    @app_commands.command(name="quero_assistir", description="Marque um filme como “quero assistir logo”.")
    @app_commands.describe(filme="Filme que você quer ver em breve")
    @app_commands.autocomplete(filme=_film_autocomplete)
    async def quero_assistir(self, interaction: discord.Interaction, filme: str) -> None:
        mv = await self._resolver(filme)
        if mv is None:
            await interaction.response.send_message(f"Não encontrei **{filme}**.", ephemeral=True)
            return
        if foi_assistido(mv.list_name):
            await interaction.response.send_message(
                f"**{mv.name}** já foi assistido pelo clube 🎬 — use `/indicar` para "
                f"indicá-lo a uma categoria.",
                ephemeral=True,
            )
            return
        await registrar_quero_assistir(interaction, mv)

    @app_commands.command(name="consenso", description="Veja o que o público mais indicou (por categoria ou geral).")
    @app_commands.describe(categoria="Categoria (ou deixe em branco para a visão geral)")
    @app_commands.autocomplete(categoria=_opcao_autocomplete)
    async def consenso(self, interaction: discord.Interaction, categoria: str | None = None) -> None:
        await interaction.response.defer()
        if not categoria:
            cats = await self.bot.db.categories_with_nominations()
            itens = []
            for cat in cats:
                rows = await self.bot.db.nomination_ranking(cat, limit=1)
                if rows:
                    _cid, nome, votos = rows[0]
                    itens.append((cat, nome, votos))
            await interaction.followup.send(embed=embeds.consenso_geral_embed(itens))
            return
        # normaliza para o nome exato da opção, se possível
        alvo = next(
            (c for c in OPCOES_INDICACAO if c.lower() == categoria.lower()), categoria
        )
        rows = await self.bot.db.nomination_ranking(alvo)
        amostras = {
            cid: await self.bot.db.nomination_samples(cid, alvo) for cid, _n, _c in rows[:3]
        }
        await interaction.followup.send(
            embed=embeds.consenso_categoria_embed(alvo, rows, amostras)
        )

    @app_commands.command(name="ranking_quero_assistir", description="Filmes com maior interesse do público.")
    async def ranking_quero_assistir(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        rows: list[tuple[str, str, int]] = []
        supabase = getattr(self.bot, "supabase", None)
        if supabase is not None:
            try:
                combined = await supabase.movie_interest_ranking(limit=15)
                for row in combined:
                    movie_key = str(row.get("movie_id", ""))
                    matches = await self.bot.catalog.por_chave_canonica(movie_key)
                    mv = next((item for item in matches if not foi_assistido(item.list_name)), None)
                    if mv is not None:
                        rows.append((movie_key, mv.name, int(row.get("interest_count") or 0)))
            except Exception as exc:  # noqa: BLE001
                log.warning("Falha ao carregar ranking combinado de interesse: %s", exc)
        if not rows:
            rows = await self.bot.db.want_ranking(limit=15)
        await interaction.followup.send(embed=embeds.want_ranking_embed(rows))

    @app_commands.command(name="minhas_indicacoes", description="Veja as indicações que você fez.")
    async def minhas_indicacoes(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.nominations_by_user(interaction.user.id)
        if not rows:
            await interaction.response.send_message(
                "Você ainda não indicou nenhum filme. Use `/indicar` ou o botão nos filmes assistidos.",
                ephemeral=True,
            )
            return
        linhas = []
        for nome, categoria, just in rows[:25]:
            txt = f"• **{nome}** → {categoria}"
            if just:
                txt += f" — _{just[:80]}_"
            linhas.append(txt)
        await interaction.response.send_message(
            "**Suas indicações:**\n" + "\n".join(linhas), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Indicacoes(bot))

