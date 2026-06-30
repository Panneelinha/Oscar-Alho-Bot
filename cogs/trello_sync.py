"""Sincroniza diariamente o placar de votos no Trello — só os números, sem
nunca revelar quem votou. Grava um bloco fixo na descrição do card (ou um
comentário), atualizando o valor a cada dia."""
from __future__ import annotations

import logging
import re
from datetime import datetime, time, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

log = logging.getLogger("oscar.trello_sync")

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # pragma: no cover - fallback se a base de tz não existir
    TZ = timezone.utc

DELIM = "———————————"
HEADER = "🗳️ Oscar Alho — votação (Discord)"
# Remove um bloco já existente (do delimitador até o fim da descrição).
_BLOCK_RE = re.compile(r"\n*" + re.escape(DELIM) + r"\n" + re.escape(HEADER) + r".*\Z", re.S)


def _montar_bloco(info: dict, data: str) -> str:
    linhas = [DELIM, HEADER]
    if info.get("nota_n"):
        linhas.append(f"🧄 Nota do clube: {info['nota']}/10 ({info['nota_n']} voto(s))")
    if info.get("indicacoes"):
        linhas.append(f"🏆 Indicações do público: {info['indicacoes']}")
    if info.get("categoria"):
        linhas.append(f"🗳️ Votos na categoria: {info['categoria']}")
    if info.get("geral"):
        linhas.append(f"👍 Curtidas: {info['geral']}")
    if info.get("quero"):
        linhas.append(f"🍿 Quero assistir logo: {info['quero']}")
    linhas.append(f"_atualizado em {data}_")
    return "\n".join(linhas)


def _aplicar_na_desc(desc: str, info: dict, data: str) -> str:
    base = _BLOCK_RE.sub("", desc or "").rstrip()
    bloco = _montar_bloco(info, data)
    return f"{base}\n\n{bloco}" if base else bloco


_CHAVES = ("geral", "categoria", "indicacoes", "quero", "nota_n")


class TrelloSync(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.modo = bot.cfg.vote_sync_mode
        self.sincronizar_diario.change_interval(
            time=time(hour=bot.cfg.trello_sync_hour, tzinfo=TZ)
        )

    async def cog_load(self) -> None:
        if self.modo != "off":
            self.sincronizar_diario.start()

    async def cog_unload(self) -> None:
        self.sincronizar_diario.cancel()

    async def _sincronizar(self) -> tuple[int, int]:
        """Escreve os números no Trello. Retorna (cards_atualizados, erros)."""
        await self.bot.catalog.refresh(force=True)
        contagens = await self.bot.db.vote_counts_per_card()
        data = datetime.now(TZ).strftime("%d/%m/%Y")
        atualizados = erros = 0
        rotulos = {
            "indicacoes": "🏆 indicações",
            "categoria": "🗳️ categoria",
            "geral": "👍 curtidas",
            "quero": "🍿 quero assistir",
        }
        for card_id, info in contagens.items():
            if not any(info.get(k) for k in _CHAVES):
                continue
            try:
                if self.modo == "comment":
                    partes = [
                        f"{rotulos[k]}: {info[k]}"
                        for k in ("indicacoes", "categoria", "geral", "quero")
                        if info.get(k)
                    ]
                    if info.get("nota_n"):
                        partes.insert(0, f"🧄 nota: {info['nota']}/10 ({info['nota_n']})")
                    await self.bot.trello.add_comment(
                        card_id, f"{HEADER} — {' · '.join(partes)} ({data})"
                    )
                else:  # modo "desc"
                    mv = await self.bot.catalog.por_id(card_id)
                    if mv is None:
                        continue  # card arquivado/fora das listas abertas
                    nova = _aplicar_na_desc(mv.desc, info, data)
                    if nova != mv.desc:
                        await self.bot.trello.update_card_desc(card_id, nova)
                        mv.desc = nova  # mantém o cache coerente
                atualizados += 1
            except Exception as e:  # noqa: BLE001
                erros += 1
                log.warning("Falha ao sincronizar card %s: %s", card_id, e)
        log.info("Sincronização com o Trello: %d atualizados, %d erros.", atualizados, erros)
        return atualizados, erros

    @tasks.loop(time=time(hour=23, tzinfo=TZ))
    async def sincronizar_diario(self) -> None:
        if self.bot.is_closed():
            return
        await self._sincronizar()

    @sincronizar_diario.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="sincronizar_trello",
        description="(admin) Grava o placar de votos no Trello agora (só números).",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def sincronizar_trello(self, interaction: discord.Interaction) -> None:
        if self.modo == "off":
            await interaction.response.send_message(
                "A sincronização com o Trello está desligada (VOTE_SYNC_MODE=off).",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        atualizados, erros = await self._sincronizar()
        await interaction.followup.send(
            f"✅ Trello atualizado: **{atualizados}** card(s)"
            + (f", {erros} erro(s)." if erros else ".")
            + f"\nModo: `{self.modo}`. Apenas números foram gravados (sigilo mantido).",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TrelloSync(bot))
