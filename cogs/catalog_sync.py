Exit code: 0
Wall time: 0.8 seconds
Output:
"""Espelha o catálogo público do Trello no Supabase.

A cada intervalo o bot consulta apenas dateLastActivity do board. O catálogo
completo só é lido quando essa marca muda; pôsteres e comentários são hidratados
somente para cards alterados.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from discord.ext import commands, tasks

from movies import Movie, canonical_movie_key, parse_comentarios

log = logging.getLogger("oscar.catalog_sync")


def _activity_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return text


def _poster_mime(attachment: dict) -> str:
    mime = str(attachment.get("mimeType") or "").lower()
    if mime.startswith("image/"):
        return mime
    suffix = Path(urlparse(str(attachment.get("url") or "")).path).suffix.lower()
    return {
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/jpeg")


def _is_image(attachment: dict) -> bool:
    mime = str(attachment.get("mimeType") or "").lower()
    url = str(attachment.get("url") or "").lower()
    return mime.startswith("image/") or url.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))


class CatalogSync(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.enabled = bool(getattr(bot, "supabase", None))
        self._board_activity = ""
        self._versions: dict[str, dict] = {}
        self.sync_catalog.change_interval(seconds=bot.cfg.trello_catalog_sync_seconds)

    async def cog_load(self) -> None:
        if self.enabled:
            self.sync_catalog.start()
            log.info(
                "Ponte Trello → Supabase ativa (detector a cada %ss).",
                self.bot.cfg.trello_catalog_sync_seconds,
            )
        else:
            log.info("Ponte Trello → Supabase desativada: credenciais não configuradas.")

    async def cog_unload(self) -> None:
        self.sync_catalog.cancel()

    async def _poster(self, card: dict, previous: dict, activity: str) -> str:
        old_payload = previous.get("payload") if isinstance(previous.get("payload"), dict) else {}
        old_poster = str(old_payload.get("poster") or "")
        cover_id = str(card.get("idAttachmentCover") or "")
        old_cover_id = str(previous.get("cover_attachment_id") or "")
        if old_poster and cover_id == old_cover_id:
            return old_poster
        if not (card.get("badges") or {}).get("attachments"):
            return "/poster-fallback.png"

        attachments = await self.bot.trello.get_card_attachments(str(card["id"]))
        images = [attachment for attachment in attachments if _is_image(attachment)]
        images.sort(key=lambda attachment: attachment.get("id") != cover_id)
        for attachment in images:
            url = str(attachment.get("url") or "")
            if not url:
                continue
            data = await self.bot.trello.download_attachment(url)
            if not data:
                continue
            filename = str(attachment.get("name") or Path(urlparse(url).path).name or "poster.jpg")
            return await self.bot.supabase.upload_movie_poster(
                str(card["id"]),
                filename,
                data,
                _poster_mime(attachment),
                activity or datetime.now(timezone.utc).isoformat(),
            )
        return old_poster or "/poster-fallback.png"

    async def _payload(
        self,
        card: dict,
        list_name: str,
        list_order: int,
        previous: dict,
        content_changed: bool,
    ) -> dict:
        movie = Movie.from_card(card, list_name)
        old_payload = previous.get("payload") if isinstance(previous.get("payload"), dict) else {}
        if content_changed:
            comments = await self.bot.trello.get_card_comments(movie.id, limit=100)
            extras = parse_comentarios(comments)
            synopsis = extras.sinopse
            trailer_url = extras.trailer_url
            genres = extras.generos
        else:
            synopsis = old_payload.get("synopsis")
            trailer_url = old_payload.get("trailerUrl")
            genres = old_payload.get("genres")

        activity = str(card.get("dateLastActivity") or "")
        poster = await self._poster(card, previous, activity)
        return {
            "id": movie.id,
            "canonicalKey": canonical_movie_key(movie),
            "title": movie.name,
            "poster": poster,
            "list": movie.list_name,
            "listOrder": list_order,
            "streaming": movie.streaming,
            "streamingDate": movie.streaming_data,
            "release": movie.estreia,
            "franchise": movie.franquia,
            "duration": movie.duracao,
            "imdb": movie.imdb_nota,
            "imdbReviews": movie.imdb_avaliacoes,
            "imdbTitle": movie.imdb_titulo,
            "imdbUrl": movie.imdb_url,
            "labels": movie.labels,
            "sessionDate": movie.sessao_data,
            "sessionProgramming": movie.sessao_programacao,
            "sessionStatus": movie.sessao_status,
            "trelloVotes": movie.votes_trello,
            "trelloUrl": movie.url,
            "description": movie.desc,
            "synopsis": synopsis,
            "trailerUrl": trailer_url,
            "genres": genres,
        }

    async def _sync(self, board_activity: str) -> None:
        lists = await self.bot.trello.get_lists_with_cards()
        current_ids: list[str] = []
        canonical_mapping: dict[str, str] = {}
        global_position = 0
        changed_count = 0

        for trello_list in sorted(lists, key=lambda item: item.get("pos", 0)):
            list_name = str(trello_list.get("name") or "")
            cards = sorted(trello_list.get("cards") or [], key=lambda item: item.get("pos", 0))
            for list_order, card in enumerate(cards):
                movie_id = str(card.get("id") or "")
                if not movie_id:
                    continue
                current_ids.append(movie_id)
                canonical_mapping[movie_id] = canonical_movie_key(Movie.from_card(card, list_name))
                previous = self._versions.get(movie_id) or {}
                old_payload = previous.get("payload") if isinstance(previous.get("payload"), dict) else {}
                activity = str(card.get("dateLastActivity") or "")
                content_changed = (
                    _activity_key(activity) != _activity_key(previous.get("trello_last_activity"))
                    or str(card.get("idAttachmentCover") or "")
                    != str(previous.get("cover_attachment_id") or "")
                )
                structure_changed = (
                    old_payload.get("list") != list_name
                    or old_payload.get("listOrder") != list_order
                    or old_payload.get("title") != str(card.get("name") or "")
                    or old_payload.get("canonicalKey")
                    != canonical_movie_key(Movie.from_card(card, list_name))
                    or previous.get("position") != global_position
                    or not previous.get("active", False)
                )
                if not content_changed and not structure_changed:
                    global_position += 1
                    continue

                payload = await self._payload(
                    card, list_name, list_order, previous, content_changed
                )
                row = {
                    "movie_id": movie_id,
                    "title": payload["title"],
                    "list_name": list_name,
                    "position": global_position,
                    "payload": payload,
                    "trello_last_activity": activity or None,
                    "cover_attachment_id": card.get("idAttachmentCover"),
                    "active": True,
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                }
                await self.bot.supabase.upsert_catalog_movie(row)
                self._versions[movie_id] = row
                changed_count += 1
                global_position += 1
                if content_changed:
                    await asyncio.sleep(0.5)

        if not current_ids:
            raise RuntimeError("o Trello devolveu um catálogo vazio; sincronização cancelada")
        await self.bot.db.rekey_movie_interactions(canonical_mapping)
        removed_count = await self.bot.supabase.deactivate_missing_catalog_movies(current_ids)
        await self.bot.supabase.set_catalog_sync_status(
            board_last_activity=board_activity,
            movie_count=len(current_ids),
        )
        self._board_activity = board_activity
        self.bot.catalog.invalidate()
        log.info(
            "Catálogo sincronizado: %s filme(s), %s alterado(s), %s removido(s).",
            len(current_ids),
            changed_count,
            removed_count,
        )

    @tasks.loop(seconds=10)
    async def sync_catalog(self) -> None:
        if self.bot.is_closed() or not self.enabled:
            return
        try:
            board_activity = await self.bot.trello.get_board_last_activity()
            if board_activity and _activity_key(board_activity) == _activity_key(self._board_activity):
                return
            await self._sync(board_activity)
        except Exception as exc:  # noqa: BLE001
            log.exception("Falha ao sincronizar catálogo Trello → Supabase: %s", exc)
            try:
                await self.bot.supabase.set_catalog_sync_status(error=str(exc))
            except Exception as status_exc:  # noqa: BLE001
                log.error("Falha ao registrar erro da sincronização: %s", status_exc)

    @sync_catalog.before_loop
    async def _before_sync(self) -> None:
        await self.bot.wait_until_ready()
        self._versions = await self.bot.supabase.catalog_versions()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CatalogSync(bot))

