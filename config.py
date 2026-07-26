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
    kick_chatroom_id: int          # id do chatroom (pro websocket de leitura), 0 = sem leitura
    supabase_url: str              # projeto Supabase do site (vazio = ponte desligada)
    supabase_service_role_key: str # chave secreta do servidor; nunca expor no navegador
    supabase_poll_seconds: int     # intervalo da fila Site → Trello

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "DISCORD_TOKEN não definido. Copie .env.example para .env e preencha."
            )
        key = os.getenv("TRELLO_API_KEY", "").strip()
        tok = os.getenv("TREL…611 tokens truncated….strip()
                or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            ),
            supabase_poll_seconds=int(supabase_poll) if supabase_poll.isdigit() and int(supabase_poll) >= 10 else 30,
        )
