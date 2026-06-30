"""Carrega a configuração a partir das variáveis de ambiente (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw)  # aceita negativos (ex.: ID de grupo do Telegram)
    except ValueError:
        return None


@dataclass(frozen=True)
class Config:
    discord_token: str
    guild_id: int | None
    announce_channel_id: int | None
    trello_key: str
    trello_token: str
    trello_board_id: str
    poll_minutes: int
    trello_sync_hour: int          # hora (0-23) da sincronização diária de votos
    vote_sync_mode: str            # "desc", "comment" ou "off"
    db_path: str                   # caminho do arquivo SQLite (volume no deploy)
    lembrete_horas: int            # quantas horas antes da sessão avisar
    lembrete_role_id: int | None   # cargo a mencionar no lembrete (opcional)
    telegram_token: str            # token do bot do Telegram ("" = desligado)
    telegram_allowed_ids: frozenset[int]  # IDs do Telegram autorizados (admins/você)
    telegram_chat_id: int | None   # chat onde postar os anúncios espelhados
    kick_channel_slug: str         # canal na Kick (ex.: "panneelinha"), "" = sem Kick
    kick_client_id: str            # app da Kick
    kick_client_secret: str
    kick_refresh_token: str        # refresh token OAuth (semente; rotaciona no DB)

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "DISCORD_TOKEN não definido. Copie .env.example para .env e preencha."
            )
        key = os.getenv("TRELLO_API_KEY", "").strip()
        tok = os.getenv("TRELLO_TOKEN", "").strip()
        if not key or not tok:
            raise RuntimeError(
                "TRELLO_API_KEY e/ou TRELLO_TOKEN não definidos. Veja o README."
            )
        poll = os.getenv("POLL_MINUTES", "30").strip()
        lembrete = os.getenv("LEMBRETE_HORAS", "3").strip()
        sync_hour = os.getenv("TRELLO_SYNC_HOUR", "23").strip()
        mode = os.getenv("VOTE_SYNC_MODE", "desc").strip().lower()
        if mode not in ("desc", "comment", "off"):
            mode = "desc"
        return cls(
            discord_token=token,
            guild_id=_int("GUILD_ID"),
            announce_channel_id=_int("ANNOUNCE_CHANNEL_ID"),
            trello_key=key,
            trello_token=tok,
            trello_board_id=os.getenv(
                "TRELLO_BOARD_ID", "6a2a1f1c8edcf60ea0226a9a"
            ).strip(),
            poll_minutes=int(poll) if poll.isdigit() else 30,
            trello_sync_hour=int(sync_hour) if sync_hour.isdigit() and 0 <= int(sync_hour) <= 23 else 23,
            vote_sync_mode=mode,
            db_path=os.getenv("DB_PATH", "oscar_alho.sqlite3").strip() or "oscar_alho.sqlite3",
            lembrete_horas=int(lembrete) if lembrete.isdigit() and int(lembrete) > 0 else 3,
            lembrete_role_id=_int("LEMBRETE_ROLE_ID"),
            telegram_token=os.getenv("TELEGRAM_TOKEN", "").strip(),
            telegram_allowed_ids=frozenset(
                int(x) for x in os.getenv("TELEGRAM_ALLOWED_IDS", "").replace(";", ",").split(",")
                if x.strip().isdigit()
            ),
            telegram_chat_id=_int("TELEGRAM_CHAT_ID"),
            kick_channel_slug=os.getenv("KICK_CHANNEL_SLUG", "").strip().lstrip("@/"),
            kick_client_id=os.getenv("KICK_CLIENT_ID", "").strip(),
            kick_client_secret=os.getenv("KICK_CLIENT_SECRET", "").strip(),
            kick_refresh_token=os.getenv("KICK_REFRESH_TOKEN", "").strip(),
        )
