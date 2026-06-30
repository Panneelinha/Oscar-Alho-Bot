"""Baixa o pôster do Trello (privado) e devolve um anexo do Discord pronto."""
from __future__ import annotations

import io

import discord

from movies import Movie
from trello_client import TrelloClient


async def poster_attachment(
    trello: TrelloClient, mv: Movie
) -> tuple[discord.File | None, str | None]:
    """Retorna (File, 'attachment://nome') para embutir no embed, ou (None, None)."""
    if not mv.tem_poster:
        return None, None
    got = await trello.get_poster(mv.id)
    if not got:
        return None, None
    data, nome = got
    return discord.File(io.BytesIO(data), filename=nome), f"attachment://{nome}"
