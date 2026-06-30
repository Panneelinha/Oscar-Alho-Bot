"""Comandos de administração do board (apenas admins):
/sugerir (cria card em FILMES A ASSISTIR) e /mover (move card entre listas)."""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from movies import LISTA_A_ASSISTIR

log = logging.getLogger("oscar.admin")


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (perms.manage_guild or perms.administrator))


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


async def _lista_autocomplete(interaction: discord.Interaction, current: str):
    nomes = await interaction.client.catalog.nomes_listas()
    cur = current.lower()
    return [
        app_commands.Choice(name=n[:100], value=n) for n in nomes if cur in n.lower()
    ][:25]


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="sugerir", description="(admin) Cria um filme em FILMES A ASSISTIR no Trello.")
    @app_commands.describe(nome="Nome do filme", observacao="Observação opcional (vai na descrição)")
    @app_commands.default_permissions(manage_guild=True)
    async def sugerir(
        self, interaction: discord.Interaction, nome: str, observacao: str | None = None
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "🔒 Só administradores podem usar este comando.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        list_id = await self.bot.catalog.list_id(LISTA_A_ASSISTIR)
        if not list_id:
            await interaction.followup.send(
                f"Não achei a lista **{LISTA_A_ASSISTIR}** no board.", ephemeral=True
            )
            return
        try:
            card = await self.bot.trello.create_card(nome, list_id, observacao or "")
        except Exception as e:  # noqa: BLE001
            log.warning("Falha ao criar card: %s", e)
            await interaction.followup.send("⚠️ Não consegui criar o card no Trello.", ephemeral=True)
            return
        self.bot.catalog.invalidate()
        await interaction.followup.send(
            f"✅ Criado **{nome}** em **{LISTA_A_ASSISTIR}**.", ephemeral=True
        )

    @app_commands.command(name="mover", description="(admin) Move um filme para outra lista do board.")
    @app_commands.describe(filme="Filme a mover", lista="Lista de destino")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.autocomplete(filme=_film_autocomplete, lista=_lista_autocomplete)
    async def mover(self, interaction: discord.Interaction, filme: str, lista: str) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "🔒 Só administradores podem usar este comando.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        mv = await self.bot.catalog.por_id(filme)
        if mv is None:
            achados = await self.bot.catalog.buscar(filme, limite=1)
            mv = achados[0] if achados else None
        if mv is None:
            await interaction.followup.send(f"Não encontrei **{filme}**.", ephemeral=True)
            return
        list_id = await self.bot.catalog.list_id(lista)
        if not list_id:
            await interaction.followup.send(f"Não achei a lista **{lista}**.", ephemeral=True)
            return
        try:
            await self.bot.trello.move_card(mv.id, list_id)
        except Exception as e:  # noqa: BLE001
            log.warning("Falha ao mover card: %s", e)
            await interaction.followup.send("⚠️ Não consegui mover o card no Trello.", ephemeral=True)
            return
        self.bot.catalog.invalidate()
        await interaction.followup.send(
            f"✅ Movi **{mv.name}** para **{lista}**.", ephemeral=True
        )


    @app_commands.command(
        name="config_canal",
        description="(admin) Define o canal deste servidor para anúncios e lembretes.",
    )
    @app_commands.describe(canal="Canal de destino (deixe em branco para usar o canal atual)")
    @app_commands.default_permissions(manage_guild=True)
    async def config_canal(
        self, interaction: discord.Interaction, canal: discord.TextChannel | None = None
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "🔒 Só administradores podem usar este comando.", ephemeral=True
            )
            return
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Use este comando dentro de um servidor.", ephemeral=True
            )
            return
        alvo = canal or interaction.channel
        await self.bot.db.set_announce_channel(interaction.guild_id, alvo.id)
        await interaction.response.send_message(
            f"✅ Anúncios e lembretes deste servidor agora vão para {alvo.mention}.\n"
            f"_Os automáticos já passam a usar esse canal (sem precisar reiniciar)._",
            ephemeral=True,
        )

    @app_commands.command(name="config_ver", description="(admin) Mostra o canal configurado neste servidor.")
    @app_commands.default_permissions(manage_guild=True)
    async def config_ver(self, interaction: discord.Interaction) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "🔒 Só administradores podem usar este comando.", ephemeral=True
            )
            return
        cid = (
            await self.bot.db.get_announce_channel(interaction.guild_id)
            if interaction.guild_id
            else None
        )
        if cid:
            ch = self.bot.get_channel(cid)
            destino = ch.mention if ch else f"`{cid}` (canal não encontrado)"
            await interaction.response.send_message(
                f"📢 Canal de anúncios/lembretes: {destino}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Nenhum canal configurado ainda. Use `/config_canal`.", ephemeral=True
            )

    @app_commands.command(name="config_remover", description="(admin) Desliga anúncios/lembretes automáticos neste servidor.")
    @app_commands.default_permissions(manage_guild=True)
    async def config_remover(self, interaction: discord.Interaction) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "🔒 Só administradores podem usar este comando.", ephemeral=True
            )
            return
        if interaction.guild_id:
            await self.bot.db.clear_announce_channel(interaction.guild_id)
        await interaction.response.send_message(
            "🛑 Anúncios/lembretes automáticos desligados neste servidor.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
