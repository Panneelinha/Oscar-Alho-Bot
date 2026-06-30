"""Ciclo da sessão:
- /proxima (próxima sessão + RSVP)
- /nota e /ranking_notas (avaliação pós-sessão)
- tarefa automática: lembrete antes da sessão + convite para avaliar depois."""
from __future__ import annotations

import html
import io
import logging
import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

import embeds
from movies import LISTA_ASSISTIDOS
from ui import rsvp_view


def _marcar_realizada_desc(desc: str, data: str) -> str:
    """Atualiza o bloco 'Sessão Oscar Alho' do card para refletir a realização."""
    novo = desc or ""
    novo = re.sub(
        r"(?m)^\*\*Status:\*\*.*$", f"**Status:** Realizada em {data}", novo, count=1
    )
    novo = re.sub(
        r"(?m)^\*\*Confirmação pós-sessão:\*\*.*$",
        f"**Confirmação pós-sessão:** Confirmada via Discord em {data}",
        novo,
        count=1,
    )
    cabecalho = "## Histórico de Sessões\n"
    entrada = f"- {data}: sessão realizada.\n"
    if cabecalho in novo:
        novo = novo.replace(cabecalho, cabecalho + entrada, 1)
    else:
        novo = novo.rstrip() + f"\n\n## Histórico de Sessões\n{entrada}"
    return novo

log = logging.getLogger("oscar.sessoes")

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # pragma: no cover
    TZ = timezone.utc

EVENT_LEMBRETE = "lembrete"
EVENT_POS = "pos_sessao"
EVENT_EVENTO = "evento_discord"
EVENT_ANUNCIO = "anuncio_sessao"
TG_GUILD = 0    # "servidor" lógico para deduplicar anúncios no Telegram
KICK_GUILD = -1  # idem para a Kick


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


class Sessoes(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.checar_sessoes.start()

    async def cog_unload(self) -> None:
        self.checar_sessoes.cancel()

    # ---------- comandos ----------
    @app_commands.command(name="proxima", description="A próxima sessão do clube + confirmação de presença.")
    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        sessao = await self.bot.catalog.proxima_sessao()
        if sessao is None:
            await interaction.followup.send("Não há sessão agendada por enquanto. Fique de olho! 🎬")
            return
        counts = (
            await self.bot.db.rsvp_counts(sessao.chave)
            if sessao.chave
            else {"vou": 0, "talvez": 0, "nao": 0}
        )
        lista_embeds = [embeds.proxima_sessao_embed(sessao, counts, self._kick_url())]
        files = []
        for f in sessao.filmes[:4]:
            poster_url = None
            if f.tem_poster:
                poster = await self.bot.trello.get_poster(f.id)
                if poster:
                    data, nome = poster
                    fname = f"{f.id}_{nome}"
                    files.append(discord.File(io.BytesIO(data), filename=fname))
                    poster_url = f"attachment://{fname}"
            lista_embeds.append(embeds.filme_resumo_embed(f, poster_url))
        view = rsvp_view(sessao.chave) if sessao.chave else None
        await interaction.followup.send(embeds=lista_embeds, files=files, view=view)

    @app_commands.command(name="nota", description="Dê sua nota (0 a 10) a um filme que você assistiu.")
    @app_commands.describe(filme="Filme avaliado", nota="Nota de 0 a 10")
    @app_commands.autocomplete(filme=_film_autocomplete)
    async def nota(
        self,
        interaction: discord.Interaction,
        filme: str,
        nota: app_commands.Range[int, 0, 10],
    ) -> None:
        mv = await self.bot.catalog.por_id(filme)
        if mv is None:
            achados = await self.bot.catalog.buscar(filme, limite=1)
            mv = achados[0] if achados else None
        if mv is None:
            await interaction.response.send_message(f"Não encontrei **{filme}**.", ephemeral=True)
            return
        await self.bot.db.set_rating(interaction.user.id, mv.id, mv.name, int(nota), interaction.guild_id)
        media, n = await self.bot.db.average_rating(mv.id)
        await interaction.response.send_message(
            f"🧄 Você deu **{nota}/10** para **{mv.name}**.\n"
            f"Média do clube agora: **{media}/10** ({n} voto(s)).",
            ephemeral=True,
        )

    @app_commands.command(name="ranking_notas", description="Filmes mais bem avaliados pelo clube.")
    async def ranking_notas(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        rows = await self.bot.db.ratings_ranking(limit=15)
        await interaction.followup.send(embed=embeds.ratings_ranking_embed(rows))

    # ---------- tarefa automática ----------
    @tasks.loop(minutes=15)
    async def checar_sessoes(self) -> None:
        if self.bot.is_closed():
            return
        targets = await self.bot.announce_targets()
        if not targets and self.bot.telegram is None:
            return
        agora = datetime.now(TZ).replace(tzinfo=None)  # parede de SP, igual ao sessao.dt
        janela = timedelta(hours=self.bot.cfg.lembrete_horas)
        try:
            sessoes = await self.bot.catalog.sessoes()
        except Exception as e:  # noqa: BLE001
            log.warning("Falha ao ler sessões: %s", e)
            return

        # na 1ª vez por servidor, não anuncia as sessões já existentes (evita rajada)
        baseline = {
            gid: (await self.bot.db.announced_count(EVENT_ANUNCIO, gid) == 0)
            for gid, _c in targets
        }
        baseline_tg = await self.bot.db.announced_count(EVENT_ANUNCIO, TG_GUILD) == 0
        baseline_kick = await self.bot.db.announced_count(EVENT_ANUNCIO, KICK_GUILD) == 0

        for s in sessoes:
            if not s.dt or not s.chave:
                continue
            if s.dt > agora:
                for gid, canal in targets:
                    guild = getattr(canal, "guild", None)
                    # cria o evento do Discord (1x por servidor)
                    if guild is not None and not await self.bot.db.already_announced(
                        s.chave, EVENT_EVENTO, gid
                    ):
                        if await self._criar_evento(guild, s):
                            await self.bot.db.mark_announced(s.chave, EVENT_EVENTO, gid)
                    # anuncia a sessão recém-confirmada (1x por servidor)
                    if not await self.bot.db.already_announced(s.chave, EVENT_ANUNCIO, gid):
                        if not baseline[gid]:
                            await self._anunciar_sessao(canal, s, "📢 Sessão confirmada!")
                        await self.bot.db.mark_announced(s.chave, EVENT_ANUNCIO, gid)
                # espelha no Telegram (1x, independente de servidor)
                if self.bot.telegram is not None and not await self.bot.db.already_announced(
                    s.chave, EVENT_ANUNCIO, TG_GUILD
                ):
                    if not baseline_tg:
                        await self.bot.notify_telegram(self._texto_sessao("📢 Sessão confirmada!", s))
                    await self.bot.db.mark_announced(s.chave, EVENT_ANUNCIO, TG_GUILD)
                # espelha no chat da Kick (1x)
                if self.bot.kick is not None and not await self.bot.db.already_announced(
                    s.chave, EVENT_ANUNCIO, KICK_GUILD
                ):
                    if not baseline_kick:
                        await self.bot.notify_kick(self._texto_kick("🎬 Sessão confirmada:", s))
                    await self.bot.db.mark_announced(s.chave, EVENT_ANUNCIO, KICK_GUILD)
            lembrar = timedelta(0) <= (s.dt - agora) <= janela
            fim = s.dt + timedelta(hours=4)
            avaliar = timedelta(0) <= (agora - fim) <= timedelta(hours=24)
            if not lembrar and not avaliar:
                continue
            for gid, canal in targets:
                if lembrar and not await self.bot.db.already_announced(s.chave, EVENT_LEMBRETE, gid):
                    await self._postar_lembrete(canal, s)
                    await self.bot.db.mark_announced(s.chave, EVENT_LEMBRETE, gid)
                if avaliar and not await self.bot.db.already_announced(s.chave, EVENT_POS, gid):
                    await self._postar_pos_sessao(canal, s)
                    await self.bot.db.mark_announced(s.chave, EVENT_POS, gid)
            # espelha o lembrete no Telegram (1x)
            if lembrar and self.bot.telegram is not None and not await self.bot.db.already_announced(
                s.chave, EVENT_LEMBRETE, TG_GUILD
            ):
                await self.bot.notify_telegram(self._texto_sessao("🔔 Lembrete de sessão!", s))
                await self.bot.db.mark_announced(s.chave, EVENT_LEMBRETE, TG_GUILD)
            # espelha o lembrete na Kick (1x)
            if lembrar and self.bot.kick is not None and not await self.bot.db.already_announced(
                s.chave, EVENT_LEMBRETE, KICK_GUILD
            ):
                await self.bot.notify_kick(self._texto_kick("🔔 Sessão chegando:", s))
                await self.bot.db.mark_announced(s.chave, EVENT_LEMBRETE, KICK_GUILD)

        # reanúncio periódico da próxima sessão (a cada N dias, por servidor)
        proxima = next((s for s in sessoes if s.dt and s.chave and s.dt > agora), None)
        if proxima is not None:
            for gid, canal in targets:
                dias_raw = await self.bot.db.get_setting(f"anuncio_dias:{gid}")
                dias = int(dias_raw) if dias_raw and dias_raw.isdigit() else 0
                if dias <= 0:
                    continue
                devido = True
                last_raw = await self.bot.db.get_setting(f"last_anuncio:{gid}")
                if last_raw:
                    try:
                        devido = (agora - datetime.fromisoformat(last_raw)) >= timedelta(days=dias)
                    except ValueError:
                        devido = True
                if devido:
                    await self._anunciar_sessao(canal, proxima, "📅 Lembrete da programação")
                    await self.bot.db.set_setting(f"last_anuncio:{gid}", agora.isoformat())

    def _kick_url(self) -> str | None:
        slug = self.bot.cfg.kick_channel_slug
        return f"https://kick.com/{slug}" if slug else None

    def _texto_kick(self, titulo: str, s) -> str:
        return f"{titulo} {s.titulo} — {s.quando}"

    def _texto_sessao(self, titulo: str, s) -> str:
        linhas = [f"<b>{html.escape(titulo)}</b>", f"🎬 {html.escape(s.titulo)}", f"📅 {html.escape(s.quando)}"]
        if s.status:
            linhas.append(f"<i>{html.escape(s.status)}</i>")
        if self._kick_url():
            linhas.append(f"🔴 Ao vivo na Kick: {self._kick_url()}")
        return "\n".join(linhas)

    async def _anunciar_sessao(self, canal, s, titulo: str) -> None:
        counts = (
            await self.bot.db.rsvp_counts(s.chave)
            if s.chave
            else {"vou": 0, "talvez": 0, "nao": 0}
        )
        embed = embeds.proxima_sessao_embed(s, counts, self._kick_url())
        embed.title = titulo
        view = rsvp_view(s.chave) if s.chave else None
        try:
            await canal.send(embed=embed, view=view)
        except discord.DiscordException as e:
            log.warning("Falha ao anunciar sessão: %s", e)

    async def _postar_lembrete(self, canal, s) -> None:
        counts = await self.bot.db.rsvp_counts(s.chave)
        embed = embeds.proxima_sessao_embed(s, counts, self._kick_url())
        embed.title = "🔔 Lembrete de sessão!"
        role = self.bot.cfg.lembrete_role_id
        content = f"<@&{role}> " if role else ""
        content += f"Tem sessão chegando: **{s.titulo}** — <t:{s.epoch}:R>!"
        try:
            await canal.send(
                content=content,
                embed=embed,
                view=rsvp_view(s.chave),
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        except discord.DiscordException as e:
            log.warning("Falha no lembrete: %s", e)

    async def _postar_pos_sessao(self, canal, s) -> None:
        nomes = ", ".join(f"**{f.name}**" for f in s.filmes) or s.titulo
        embed = discord.Embed(
            title="🎬 Como foi a sessão?",
            color=embeds.COR,
            description=(
                f"A sessão de {nomes} já rolou! Avalie com **`/nota`** (0 a 10) — "
                f"a média do clube vai pra ficha do filme e pro Trello. 🧄"
            ),
        )
        try:
            await canal.send(embed=embed)
        except discord.DiscordException as e:
            log.warning("Falha no convite pós-sessão: %s", e)

    # ---------- evento do Discord ----------
    async def _criar_evento(self, guild: discord.Guild, s) -> bool:
        if guild.me is None or not guild.me.guild_permissions.manage_events:
            return False
        inicio = s.dt.replace(tzinfo=TZ)
        fim = inicio + timedelta(hours=4)
        desc_linhas = []
        for f in s.filmes:
            linha = f"• {f.name}"
            if f.imdb_nota:
                linha += f" (IMDb {f.imdb_nota})"
            desc_linhas.append(linha)
        descricao = "Sessão do Oscar Alho 🧄\n" + "\n".join(desc_linhas)
        try:
            await guild.create_scheduled_event(
                name=f"🎬 {s.titulo}"[:100],
                description=descricao[:1000],
                start_time=inicio,
                end_time=fim,
                entity_type=discord.EntityType.external,
                location="Sessão do Oscar Alho 🍿",
                privacy_level=discord.PrivacyLevel.guild_only,
            )
            log.info("Evento criado no guild %s para a sessão %s", guild.id, s.chave)
            return True
        except discord.DiscordException as e:
            log.warning("Falha ao criar evento no guild %s: %s", guild.id, e)
            return False

    @app_commands.command(name="criar_evento", description="(admin) Cria os eventos do Discord para as próximas sessões.")
    @app_commands.default_permissions(manage_events=True)
    async def criar_evento(self, interaction: discord.Interaction) -> None:
        if not _is_admin(interaction) or interaction.guild is None:
            await interaction.response.send_message("🔒 Apenas administradores, em um servidor.", ephemeral=True)
            return
        if not interaction.guild.me.guild_permissions.manage_events:
            await interaction.response.send_message(
                "⚠️ Preciso da permissão **Gerenciar Eventos** para criar os eventos do Discord.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        agora = datetime.now(TZ).replace(tzinfo=None)
        sessoes = await self.bot.catalog.sessoes()
        criados = pulados = 0
        for s in sessoes:
            if not s.dt or not s.chave or s.dt <= agora:
                continue
            if await self.bot.db.already_announced(s.chave, EVENT_EVENTO, interaction.guild.id):
                pulados += 1
                continue
            if await self._criar_evento(interaction.guild, s):
                await self.bot.db.mark_announced(s.chave, EVENT_EVENTO, interaction.guild.id)
                criados += 1
        await interaction.followup.send(
            f"✅ **{criados}** evento(s) criado(s)."
            + (f" ({pulados} já existiam)." if pulados else ""),
            ephemeral=True,
        )

    # ---------- marcar sessão como realizada ----------
    async def _sessao_ac(self, interaction: discord.Interaction, current: str):
        sessoes = await self.bot.catalog.sessoes()
        cur = current.lower()
        out = []
        for s in sessoes:
            if not s.chave:
                continue
            label = f"{s.quando} — {s.titulo}"
            if cur in label.lower():
                out.append(app_commands.Choice(name=label[:100], value=s.chave))
        return out[:25]

    @app_commands.command(name="sessao_realizada", description="(admin) Marca uma sessão como realizada (atualiza o Trello).")
    @app_commands.describe(
        sessao="Sessão a marcar como realizada",
        mover="Mover os filmes para ASSISTIDOS (padrão: sim)",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def sessao_realizada(
        self, interaction: discord.Interaction, sessao: str, mover: bool = True
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message("🔒 Apenas administradores.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        self.bot.catalog.invalidate()
        sessoes = await self.bot.catalog.sessoes()
        s = next((x for x in sessoes if x.chave == sessao), None)
        if s is None:
            await interaction.followup.send("Sessão não encontrada.", ephemeral=True)
            return
        data = datetime.now(TZ).strftime("%d/%m/%Y")
        assistidos_id = await self.bot.catalog.list_id(LISTA_ASSISTIDOS) if mover else None
        atualizados = movidos = 0
        for f in s.filmes:
            try:
                nova = _marcar_realizada_desc(f.desc, data)
                if nova != f.desc:
                    await self.bot.trello.update_card_desc(f.id, nova)
                    f.desc = nova
                atualizados += 1
                if mover and assistidos_id:
                    await self.bot.trello.move_card(f.id, assistidos_id)
                    movidos += 1
            except Exception as e:  # noqa: BLE001
                log.warning("Falha ao marcar realizada (%s): %s", f.name, e)
        self.bot.catalog.invalidate()
        # convite de avaliação + impede o convite automático de repetir
        targets = await self.bot.announce_targets()
        for gid, canal in targets:
            try:
                await self._postar_pos_sessao(canal, s)
            except discord.DiscordException:
                pass
            await self.bot.db.mark_announced(s.chave, EVENT_POS, gid)
        # anuncia automaticamente a próxima sessão (se houver outra)
        proxima = await self.bot.catalog.proxima_sessao()
        anunciou_proxima = False
        if proxima and proxima.chave and proxima.chave != s.chave:
            for gid, canal in targets:
                await self._anunciar_sessao(canal, proxima, "🎬 E a próxima sessão é…")
                # marca como já anunciada p/ a tarefa não repetir
                await self.bot.db.mark_announced(proxima.chave, EVENT_ANUNCIO, gid)
            await self.bot.notify_telegram(self._texto_sessao("🎬 E a próxima sessão é…", proxima))
            await self.bot.db.mark_announced(proxima.chave, EVENT_ANUNCIO, TG_GUILD)
            await self.bot.notify_kick(self._texto_kick("🎬 Próxima sessão:", proxima))
            await self.bot.db.mark_announced(proxima.chave, EVENT_ANUNCIO, KICK_GUILD)
            anunciou_proxima = True
        msg = f"✅ Sessão **{s.titulo}** marcada como **realizada** ({data})."
        msg += f"\n📝 {atualizados} card(s) atualizados no Trello."
        if mover:
            msg += f"\n📦 {movidos} movido(s) para **{LISTA_ASSISTIDOS}**."
        if targets:
            msg += "\n🧄 Convite de avaliação enviado."
        if anunciou_proxima:
            msg += f"\n📢 Próxima sessão anunciada: **{proxima.titulo}**."
        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="config_anuncios", description="(admin) Reanuncia a próxima sessão a cada N dias (0 = desligar).")
    @app_commands.describe(dias="Intervalo em dias (0 para desligar)")
    @app_commands.default_permissions(manage_guild=True)
    async def config_anuncios(
        self, interaction: discord.Interaction, dias: app_commands.Range[int, 0, 30]
    ) -> None:
        if not _is_admin(interaction) or interaction.guild is None:
            await interaction.response.send_message("🔒 Apenas administradores, em um servidor.", ephemeral=True)
            return
        await self.bot.db.set_setting(f"anuncio_dias:{interaction.guild.id}", str(int(dias)))
        await self.bot.db.set_setting(f"last_anuncio:{interaction.guild.id}", "")
        if dias > 0:
            msg = (
                f"📣 Vou reanunciar a próxima sessão a cada **{dias}** dia(s) neste servidor "
                f"(o primeiro sai já já)."
            )
        else:
            msg = "🛑 Reanúncio periódico desligado."
        await interaction.response.send_message(msg, ephemeral=True)

    @sessao_realizada.autocomplete("sessao")
    async def _sr_ac(self, interaction: discord.Interaction, current: str):
        return await self._sessao_ac(interaction, current)

    @checar_sessoes.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Sessoes(bot))
