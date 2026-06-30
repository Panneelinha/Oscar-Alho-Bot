"""/ajuda — guia interativo do bot, com menu de navegação por tópicos."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from embeds import COR

RODAPE = "Oscar Alho 🧄 • use o menu abaixo para navegar"


def _base(titulo: str, descricao: str | None = None) -> discord.Embed:
    e = discord.Embed(title=titulo, description=descricao, color=COR)
    e.set_footer(text=RODAPE)
    return e


def emb_inicio() -> discord.Embed:
    e = _base(
        "🎬 Guia do Oscar Alho",
        "Eu sou o assistente do clube de cinema **Oscar Alho**, ligado ao quadro do "
        "Trello. Ajudo com a **programação**, **fichas de filmes**, **indicações**, "
        "**cerimônia de premiação**, **bolão** e muito mais.\n\n"
        "👉 Use o **menu abaixo** para explorar cada parte.",
    )
    e.add_field(
        name="Comece por aqui",
        value=(
            "• `/programacao` — o que vem por aí\n"
            "• `/proxima` — a próxima sessão (com presença)\n"
            "• `/filme <nome>` — ficha de um filme\n"
            "• `/perfil` — seus pontos e nível"
        ),
        inline=False,
    )
    e.add_field(
        name="Como o clube funciona, em resumo",
        value=(
            "1️⃣ Programamos sessões → 2️⃣ assistimos → 3️⃣ avaliamos (`/nota`)\n"
            "4️⃣ indicamos a prêmios → 5️⃣ cerimônia elege os vencedores → "
            "6️⃣ tudo vira **pontos** 🌟"
        ),
        inline=False,
    )
    return e


def emb_sessoes() -> discord.Embed:
    e = _base("🎬 Programação & Sessões")
    e.add_field(
        name="Consultar",
        value=(
            "• `/programacao` — próximas sessões + o que está no streaming\n"
            "• `/proxima` — a próxima sessão com pôsteres e **botões de presença** "
            "(✅ Vou / 🤔 Talvez / ❌ Não vou)"
        ),
        inline=False,
    )
    e.add_field(
        name="Automático",
        value=(
            "🔔 **Lembrete** no canal antes da sessão\n"
            "📅 **Evento do Discord** criado para cada sessão (você marca *Interessado*)"
        ),
        inline=False,
    )
    e.add_field(
        name="Depois de assistir",
        value=(
            "• `/nota <filme> <0-10>` — dê sua nota; calculo a **média do clube**\n"
            "• `/ranking_notas` — filmes mais bem avaliados"
        ),
        inline=False,
    )
    return e


def emb_filmes() -> discord.Embed:
    e = _base("🍿 Filmes & Catálogo")
    e.add_field(
        name="Comandos",
        value=(
            "• `/filme <nome>` — ficha completa: pôster, sinopse, trailer, "
            "nota do IMDb e do clube, gêneros e etiquetas\n"
            "• `/catalogo [categoria]` — lista as categorias ou os filmes de uma\n"
            "• `/indicados <categoria>` — indicados oficiais de uma categoria\n"
            "• `/estatisticas` — panorama do clube (catálogo + participação)"
        ),
        inline=False,
    )
    e.add_field(
        name="💡 Dica",
        value="No `/filme` e nos anúncios há um **botão** que muda conforme o filme — veja o tópico *Indicações*.",
        inline=False,
    )
    return e


def emb_votos() -> discord.Embed:
    e = _base("👍 Curtidas & “Quero assistir”")
    e.add_field(
        name="O botão dos filmes",
        value=(
            "Em cada filme há um botão que muda conforme o estado:\n"
            "• Já assistido → **🏆 Indicar a um prêmio**\n"
            "• Ainda não assistido → **🍿 Quero assistir logo**"
        ),
        inline=False,
    )
    e.add_field(
        name="Comandos",
        value=(
            "• `/votar <filme>` — curtir (clique de novo para tirar)\n"
            "• `/ranking` — filmes mais curtidos · `/meusvotos`\n"
            "• `/quero_assistir <filme>` — pra eu priorizar no agendamento\n"
            "• `/ranking_quero_assistir` — os mais pedidos"
        ),
        inline=False,
    )
    return e


def emb_indicacoes() -> discord.Embed:
    e = _base(
        "🏆 Indicações & Cerimônia",
        "A premiação acontece em **fases**. Veja a fase atual com `/cerimonia_status`.",
    )
    e.add_field(
        name="1) Indicar (todos)",
        value=(
            "Botão **🏆 Indicar** ou `/indicar` → escolhe a categoria (ou 🚫 *Fora da "
            "premiação*) e justifica. Sua indicação vira **comentário no Trello** com seu nome.\n"
            "• `/consenso [categoria]` — o que o público mais indicou\n"
            "• `/minhas_indicacoes` — o que você indicou"
        ),
        inline=False,
    )
    e.add_field(
        name="2) Votar (todos)",
        value=(
            "• `/votar_categoria` — cédula secreta entre os indicados\n"
            "• `/votar_final <categoria>` — voto no vencedor (só na fase de votação)\n"
            "• `/ranking_categoria` · `/apuracao` (cédula × indicações)"
        ),
        inline=False,
    )
    e.add_field(
        name="3) Cerimônia (admin)",
        value="O admin abre a votação, e depois revela os vencedores com pompa. Veja *Admin*.",
        inline=False,
    )
    return e


def emb_bolao() -> discord.Embed:
    e = _base(
        "🎰 Bolão",
        "Durante a fase de **votação**, aposte em quem vai vencer. Quando a cerimônia "
        "acontece, conto os acertos (1 ponto cada).",
    )
    e.add_field(
        name="Comandos",
        value=(
            "• `/palpite <categoria>` — aposte no vencedor\n"
            "• `/meus_palpites` — suas apostas\n"
            "• `/bolao_ranking` — ranking de acertos (sai após a cerimônia)"
        ),
        inline=False,
    )
    return e


def emb_gamificacao() -> discord.Embed:
    e = _base(
        "🌟 Gamificação",
        "Tudo que você faz vira **pontos** e sobe seu **nível**.",
    )
    e.add_field(
        name="Como pontuar",
        value=(
            "👍 Curtir / 🍿 Quero assistir → **+1**\n"
            "🎟️ Presença / 🗳️ Voto de categoria / 🎰 Palpite → **+2**\n"
            "🧄 Dar nota / 🏆 Indicar / 🎬 Voto final → **+3**\n"
            "🎙️ Tempo na call do cinema → **+1 a cada 15 min** (até 6/sessão)\n"
            "🎯 Acertar no bolão → **+5**"
        ),
        inline=False,
    )
    e.add_field(
        name="Níveis",
        value="🎟️ Figurante → 🍿 Espectador → 🎬 Cinéfilo → ⭐ Crítico → 🏆 Jurado do Alho → 👑 Lenda do Alho",
        inline=False,
    )
    e.add_field(
        name="Comandos",
        value="• `/perfil [membro]` — pontos, nível e participação\n• `/ranking_pontos` — os mais participativos",
        inline=False,
    )
    return e


def emb_admin() -> discord.Embed:
    e = _base(
        "🔧 Administração",
        "🔒 Comandos só para administradores (quem tem **Gerenciar Servidor**).",
    )
    e.add_field(
        name="Configuração do servidor",
        value=(
            "• `/config_canal [#canal]` — define o canal de anúncios/lembretes deste servidor\n"
            "• `/config_ver` · `/config_remover`\n"
            "• `/config_cargos ativar:True` — cria/atribui **cargos por nível** (precisa de *Gerenciar Cargos*)\n"
            "• `/sincronizar_cargos` — aplica os cargos a todos\n"
            "• `/config_cinema <canal>` — canal de voz que dá **pontos por tempo na sessão**"
        ),
        inline=False,
    )
    e.add_field(
        name="Board (Trello)",
        value=(
            "• `/sugerir <nome>` — cria filme em *Filmes a assistir*\n"
            "• `/mover <filme> <lista>` — move o card entre listas\n"
            "• `/anunciar <filme>` — anuncia um filme no canal\n"
            "• `/sincronizar_trello` — grava o placar de votos (só números) no Trello"
        ),
        inline=False,
    )
    e.add_field(
        name="Sessões",
        value=(
            "• `/criar_evento` — cria os eventos do Discord (precisa de *Gerenciar Eventos*)\n"
            "• `/sessao_realizada <sessao>` — marca como realizada, atualiza o Trello, move os filmes "
            "e **anuncia a próxima**\n"
            "• `/config_anuncios <dias>` — reanuncia a próxima sessão a cada N dias (0 desliga)\n"
            "ℹ️ Sessões recém-confirmadas no Trello são **anunciadas automaticamente**."
        ),
        inline=False,
    )
    e.add_field(
        name="Cerimônia",
        value=(
            "• `/abrir_votacao [n]` — trava os finalistas e abre a votação\n"
            "• `/cerimonia` — revela os vencedores (+ resultado do bolão)\n"
            "• `/reabrir_indicacoes` — volta para a fase de indicações (zera finalistas/votos/palpites)"
        ),
        inline=False,
    )
    return e


PAGINAS: list[tuple[str, str, object]] = [
    ("inicio", "🏠 Início", emb_inicio),
    ("sessoes", "🎬 Programação & Sessões", emb_sessoes),
    ("filmes", "🍿 Filmes & Catálogo", emb_filmes),
    ("votos", "👍 Curtidas & Quero assistir", emb_votos),
    ("indicacoes", "🏆 Indicações & Cerimônia", emb_indicacoes),
    ("bolao", "🎰 Bolão", emb_bolao),
    ("gamificacao", "🌟 Gamificação", emb_gamificacao),
    ("admin", "🔧 Administração", emb_admin),
]


class _AjudaSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label=label, value=key) for key, label, _b in PAGINAS
        ]
        super().__init__(placeholder="📖 Escolha um tópico…", options=options)
        self._builders = {key: b for key, _l, b in PAGINAS}

    async def callback(self, interaction: discord.Interaction) -> None:
        builder = self._builders[self.values[0]]
        await interaction.response.edit_message(embed=builder(), view=self.view)


class AjudaView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=300)
        self.add_item(_AjudaSelect())


class Ajuda(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ajuda", description="Guia do bot: o que cada comando faz (usuário e admin).")
    async def ajuda(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=emb_inicio(), view=AjudaView(), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ajuda(bot))
