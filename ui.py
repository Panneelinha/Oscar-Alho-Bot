"""Componentes interativos do público (botão persistente nos anúncios/fichas):
- filme JÁ assistido  -> indicar a uma categoria (+ justificativa -> comentário no Trello)
- filme NÃO assistido -> "Quero assistir logo" (preferência de agendamento)
"""
from __future__ import annotations

import logging

import discord

from movies import (
    CATEGORIAS_PREMIACAO,
    LISTA_FORA_PREMIACAO,
    Movie,
    foi_assistido,
)

log = logging.getLogger("oscar.ui")


# ---------- fluxo: quero assistir logo ----------
async def registrar_quero_assistir(interaction: discord.Interaction, mv: Movie) -> None:
    bot = interaction.client
    add = await bot.db.toggle_want(  # type: ignore[attr-defined]
        interaction.user.id, mv.id, mv.name, interaction.guild_id
    )
    total = await bot.db.count_want(mv.id)  # type: ignore[attr-defined]
    if add:
        msg = (
            f"🍿 **{mv.name}** ainda não foi assistido pelo clube, então não dá pra "
            f"indicar a prêmios *ainda*.\n"
            f"Mas anotei seu **“Quero assistir logo”**! Já são **{total}** interessado(s) "
            f"— isso ajuda a priorizar o agendamento. 🎬"
        )
    else:
        msg = f"↩️ Tirei seu “Quero assistir logo” de **{mv.name}** (agora {total})."
    await interaction.response.send_message(msg, ephemeral=True)


# ---------- fluxo: indicar a uma categoria ----------
class _JustificativaModal(discord.ui.Modal):
    def __init__(self, mv: Movie, categoria: str) -> None:
        self.fora = categoria == LISTA_FORA_PREMIACAO
        super().__init__(
            title="Fora da premiação" if self.fora else f"Indicar: {categoria[:30]}"
        )
        self.mv = mv
        self.categoria = categoria
        self.justificativa = discord.ui.TextInput(
            label=(
                "Por que NÃO deveria concorrer? (opcional)"
                if self.fora
                else "Por que merece concorrer? (opcional)"
            ),
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=900,
            placeholder="Pode deixar em branco mesmo assim.",
        )
        self.add_item(self.justificativa)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        bot = interaction.client
        autor = interaction.user.display_name
        texto = (self.justificativa.value or "").strip()
        nova = await bot.db.add_nomination(  # type: ignore[attr-defined]
            interaction.user.id, self.mv.id, self.mv.name, self.categoria, texto,
            interaction.guild_id,
        )
        cabecalho = (
            "🚫 Indicação para FORA DA PREMIAÇÃO (via Discord)"
            if self.fora
            else f"🏆 Indicação (via Discord) — Categoria: {self.categoria}"
        )
        comentario = f"{cabecalho}\nAutor: {autor}\nJustificativa: {texto or '—'}"
        try:
            await bot.trello.add_comment(self.mv.id, comentario)  # type: ignore[attr-defined]
            trello_ok = True
        except Exception as e:  # noqa: BLE001
            trello_ok = False
            log.warning("Falha ao comentar indicação no Trello: %s", e)

        if self.fora:
            base = (
                f"✅ Registrado: você acha que **{self.mv.name}** deve ficar **fora da premiação**."
                if nova
                else f"🔁 Você já tinha marcado **{self.mv.name}** como fora da premiação; atualizei sua justificativa."
            )
        else:
            base = (
                f"✅ Indicação registrada: **{self.mv.name}** → **{self.categoria}**."
                if nova
                else f"🔁 Você já tinha indicado **{self.mv.name}** a **{self.categoria}**; atualizei sua justificativa."
            )
        if trello_ok:
            base += "\nFoi salva como comentário no Trello com o seu nome. 📝"
        else:
            base += "\n⚠️ Não consegui salvar no Trello agora (mas guardei aqui)."
        base += "\n\nQuer indicar a **outra** categoria? É só clicar de novo. 😉"
        await interaction.response.send_message(base, ephemeral=True)


class _CategoriaSelect(discord.ui.Select):
    def __init__(self, mv: Movie) -> None:
        self.mv = mv
        options = [
            discord.SelectOption(label=c[:100], value=c) for c in CATEGORIAS_PREMIACAO
        ]
        options.append(
            discord.SelectOption(
                label="Fora da premiação",
                value=LISTA_FORA_PREMIACAO,
                emoji="🚫",
                description="Acho que NÃO deveria concorrer",
            )
        )
        super().__init__(
            placeholder="Escolha a categoria (ou tire da disputa)…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_JustificativaModal(self.mv, self.values[0]))


class IndicacaoView(discord.ui.View):
    def __init__(self, mv: Movie) -> None:
        super().__init__(timeout=180)
        self.add_item(_CategoriaSelect(mv))


async def abrir_indicacao(interaction: discord.Interaction, mv: Movie) -> None:
    """Mostra o menu de categorias (filme já assistido)."""
    await interaction.response.send_message(
        f"🏆 Indique **{mv.name}** a uma categoria do Oscar Alho — ou marque como "
        f"**🚫 fora da premiação**.\n"
        f"_Você pode escolher mais de uma — uma de cada vez._",
        view=IndicacaoView(mv),
        ephemeral=True,
    )


# ---------- botão persistente ----------
class InteragirButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"oscar:vote:(?P<card_id>[A-Za-z0-9]+)",
):
    """Botão que, ao ser clicado, decide entre INDICAR ou QUERO ASSISTIR conforme
    o estado atual do filme no board."""

    def __init__(self, card_id: str, label: str = "⭐ Interagir") -> None:
        self.card_id = card_id
        super().__init__(
            discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.success,
                custom_id=f"oscar:vote:{card_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match) -> "InteragirButton":
        return cls(match["card_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        mv = await interaction.client.catalog.por_id(self.card_id)  # type: ignore[attr-defined]
        if mv is None:
            await interaction.response.send_message(
                "Não encontrei esse filme no board agora 😕", ephemeral=True
            )
            return
        if foi_assistido(mv.list_name):
            await abrir_indicacao(interaction, mv)
        else:
            await registrar_quero_assistir(interaction, mv)


def vote_view(mv: Movie) -> discord.ui.View:
    """View com o botão certo para o estado do filme."""
    label = "🏆 Indicar a um prêmio" if foi_assistido(mv.list_name) else "🍿 Quero assistir logo"
    view = discord.ui.View(timeout=None)
    view.add_item(InteragirButton(mv.id, label=label))
    return view


# ---------- RSVP de sessões ----------
_RSVP_LABEL = {"vou": "✅ Vou", "talvez": "🤔 Talvez", "nao": "❌ Não vou"}
_RSVP_STYLE = {
    "vou": discord.ButtonStyle.success,
    "talvez": discord.ButtonStyle.secondary,
    "nao": discord.ButtonStyle.danger,
}
_RSVP_MSG = {"vou": "presença confirmada", "talvez": "marcado como *talvez*", "nao": "ausência registrada"}


class RSVPButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"rsvp:(?P<status>vou|talvez|nao):(?P<key>\d+)",
):
    def __init__(self, status: str, key: str) -> None:
        self.status = status
        self.key = key
        super().__init__(
            discord.ui.Button(
                label=_RSVP_LABEL[status],
                style=_RSVP_STYLE[status],
                custom_id=f"rsvp:{status}:{key}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match) -> "RSVPButton":
        return cls(match["status"], match["key"])

    async def callback(self, interaction: discord.Interaction) -> None:
        import embeds

        bot = interaction.client
        await bot.db.set_rsvp(  # type: ignore[attr-defined]
            interaction.user.id, self.key, self.status, interaction.guild_id
        )
        counts = await bot.db.rsvp_counts(self.key)  # type: ignore[attr-defined]
        # atualiza o campo "Presença" da mensagem, se possível
        try:
            msg = interaction.message
            if msg and msg.embeds:
                lista = msg.embeds  # preserva todos os embeds (sessão + filmes)
                val = embeds._linha_rsvp(counts)
                for emb in lista:
                    idx = next(
                        (i for i, f in enumerate(emb.fields) if f.name == "Presença"),
                        None,
                    )
                    if idx is not None:
                        emb.set_field_at(idx, name="Presença", value=val, inline=False)
                        break
                # edita mantendo TODOS os embeds e os anexos (pôsteres)
                await msg.edit(embeds=lista)
        except Exception:  # noqa: BLE001
            pass
        await interaction.response.send_message(
            f"{_RSVP_LABEL[self.status]} — {_RSVP_MSG[self.status]}! "
            f"(✅ {counts['vou']} · 🤔 {counts['talvez']} · ❌ {counts['nao']})",
            ephemeral=True,
        )


def rsvp_view(session_key: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for status in ("vou", "talvez", "nao"):
        view.add_item(RSVPButton(status, session_key))
    return view
