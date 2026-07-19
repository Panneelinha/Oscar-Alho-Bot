"""Consome a fila do Supabase e espelha interações do site no Trello.

A fila (outbox) torna a ponte tolerante a reinícios. O bot é o único componente
que recebe a service_role e as credenciais privadas do Trello.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from discord.ext import commands, tasks

log = logging.getLogger("oscar.site_sync")

DELIM = "───────────"
HEADER = "🌐 Oscar Alho — interação do site"
_BLOCK_RE = re.compile(r"\n*" + re.escape(DELIM) + r"\n" + re.escape(HEADER) + r".*?" + re.escape(DELIM), re.S)


def _apply_site_votes(desc: str, count: int) -> str:
    base = _BLOCK_RE.sub("", desc or "").rstrip()
    bloco = f"{DELIM}\n{HEADER}\n💜 Quero ver: {count} voto(s)\n_atualizado em {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}_\n{DELIM}"
    return f"{base}\n\n{bloco}" if base else bloco


class SiteSync(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.enabled = bool(getattr(bot, "supabase", None))
        self.consume.change_interval(seconds=bot.cfg.supabase_poll_seconds)

    async def cog_load(self) -> None:
        if self.enabled:
            self.consume.start()
            log.info("Ponte Supabase → Trello ativa (intervalo %ss).", self.bot.cfg.supabase_poll_seconds)
        else:
            log.info("Ponte Supabase → Trello desativada: credenciais não configuradas.")

    async def cog_unload(self) -> None:
        self.consume.cancel()

    async def _profile_name(self, payload: dict) -> str:
        profile = await self.bot.supabase.profile(str(payload.get("user_id", "")))
        return (profile.get("display_name") or "Membro do clube").strip()

    async def _already_commented(self, card_id: str, marker: str) -> bool:
        comments = await self.bot.trello.get_card_comments(card_id, limit=100)
        return any(marker in comment for comment in comments)

    async def _handle_comment(self, event: dict, payload: dict) -> None:
        card_id = str(payload.get("movie_id", ""))
        body = str(payload.get("body", "")).strip()
        if not card_id or not body:
            raise ValueError("comentário sem movie_id/body")
        marker = f"[site-event:{event['id']}]"
        if await self._already_commented(card_id, marker):
            return
        author = await self._profile_name(payload)
        await self.bot.trello.add_comment(
            card_id,
            f"💬 Site Oscar Alho — {author}\n{body}\n\n{marker}",
        )

    async def _handle_vote(self, payload: dict) -> None:
        card_id = str(payload.get("movie_id", ""))
        if not card_id:
            raise ValueError("voto sem movie_id")
        count = await self.bot.supabase.movie_vote_count(card_id)
        movie = await self.bot.catalog.por_id(card_id)
        if movie is None:
            raise ValueError(f"card {card_id} não encontrado no catálogo")
        new_desc = _apply_site_votes(movie.desc, count)
        if new_desc != movie.desc:
            await self.bot.trello.update_card_desc(card_id, new_desc)
            movie.desc = new_desc

    async def _handle_nomination(self, event: dict, payload: dict) -> None:
        card_id = str(payload.get("movie_id", ""))
        category = str(payload.get("category", "")).strip()
        justification = str(payload.get("justification", "")).strip()
        if not card_id or not category or not justification:
            raise ValueError("indicação sem movie_id/categoria/justificativa")
        marker = f"[site-event:{event['id']}]"
        if await self._already_commented(card_id, marker):
            return
        author = await self._profile_name(payload)
        prefix = (
            "🚫 Indicação para FORA DA PREMIAÇÃO (via site)"
            if category == "FORA DA PREMIAÇÃO"
            else f"🏆 Indicação (via site) — Categoria: {category}"
        )
        await self.bot.trello.add_comment(
            card_id,
            f"{prefix}\nAutor: {author}\nJustificativa: {justification}\n\n{marker}",
        )

    async def _handle_rsvp(self, event: dict, payload: dict) -> None:
        card_id = str(payload.get("movie_id", ""))
        if not card_id:
            raise ValueError("presença sem movie_id")
        marker = f"[site-event:{event['id']}]"
        if await self._already_commented(card_id, marker):
            return
        author = await self._profile_name(payload)
        labels = {"vou": "vai à sessão", "talvez": "talvez vá à sessão", "nao": "não vai à sessão"}
        status = labels.get(str(payload.get("status", "")), "atualizou a presença")
        await self.bot.trello.add_comment(
            card_id,
            f"📅 Site Oscar Alho — {author} {status}.\n\n{marker}",
        )

    async def _handle(self, event: dict) -> None:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_type = event.get("event_type")
        if event_type == "comment.created":
            await self._handle_comment(event, payload)
        elif event_type == "vote.changed":
            await self._handle_vote(payload)
        elif event_type == "rsvp.changed":
            await self._handle_rsvp(event, payload)
        elif event_type == "nomination.created":
            await self._handle_nomination(event, payload)
        else:
            raise ValueError(f"tipo de evento desconhecido: {event_type}")

    @tasks.loop(seconds=30)
    async def consume(self) -> None:
        if self.bot.is_closed() or not self.enabled:
            return
        events = await self.bot.supabase.claim_events(20)
        for event in events:
            try:
                await self._handle(event)
                await self.bot.supabase.mark_processed(int(event["id"]))
            except Exception as exc:  # noqa: BLE001
                log.warning("Falha no evento Supabase %s: %s", event.get("id"), exc)
                try:
                    await self.bot.supabase.mark_failed(
                        int(event["id"]), str(exc), int(event.get("attempts", 1))
                    )
                except Exception as mark_exc:  # noqa: BLE001
                    log.error("Falha ao devolver evento %s para retry: %s", event.get("id"), mark_exc)

    @consume.before_loop
    async def _before_consume(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SiteSync(bot))