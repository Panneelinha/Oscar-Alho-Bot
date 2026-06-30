"""Persistência local (SQLite via aiosqlite): votos dos membros e controle
de quais cards já foram anunciados."""
from __future__ import annotations

import aiosqlite

DB_PATH = "oscar_alho.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS votes (
    user_id   INTEGER NOT NULL,
    card_id   TEXT    NOT NULL,
    card_name TEXT    NOT NULL,
    guild_id  INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, card_id)
);
-- Controle de "já postado", por servidor (evita anúncio/lembrete duplicado).
CREATE TABLE IF NOT EXISTS event_log (
    card_id  TEXT    NOT NULL,
    event    TEXT    NOT NULL,
    guild_id INTEGER NOT NULL DEFAULT 0,
    at       TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (card_id, event, guild_id)
);
-- Configuração por servidor (canal de anúncios/lembretes).
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id            INTEGER PRIMARY KEY,
    announce_channel_id INTEGER
);
-- Cédula por categoria: 1 voto por usuário por categoria (votar de novo troca).
CREATE TABLE IF NOT EXISTS category_votes (
    user_id    INTEGER NOT NULL,
    category   TEXT    NOT NULL,
    card_id    TEXT    NOT NULL,
    card_name  TEXT    NOT NULL,
    guild_id   INTEGER,
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, category)
);
-- Indicações do público: 1 por (usuário, filme, categoria), com justificativa.
CREATE TABLE IF NOT EXISTS nominations (
    user_id       INTEGER NOT NULL,
    card_id       TEXT    NOT NULL,
    card_name     TEXT    NOT NULL,
    category      TEXT    NOT NULL,
    justificativa TEXT,
    guild_id      INTEGER,
    updated_at    TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, card_id, category)
);
-- "Quero assistir logo": interesse do público em filmes ainda não assistidos.
CREATE TABLE IF NOT EXISTS want_to_watch (
    user_id    INTEGER NOT NULL,
    card_id    TEXT    NOT NULL,
    card_name  TEXT    NOT NULL,
    guild_id   INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, card_id)
);
-- Notas pós-sessão: 0 a 10, 1 nota por usuário por filme.
CREATE TABLE IF NOT EXISTS ratings (
    user_id    INTEGER NOT NULL,
    card_id    TEXT    NOT NULL,
    card_name  TEXT    NOT NULL,
    nota       INTEGER NOT NULL,
    guild_id   INTEGER,
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, card_id)
);
-- Presença nas sessões (RSVP): 1 resposta por usuário por sessão.
CREATE TABLE IF NOT EXISTS rsvp (
    user_id     INTEGER NOT NULL,
    session_key TEXT    NOT NULL,
    status      TEXT    NOT NULL,   -- vou | talvez | nao
    guild_id    INTEGER,
    updated_at  TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, session_key)
);
-- Tempo na call (cinema) por sessão, em segundos, para pontuar.
CREATE TABLE IF NOT EXISTS voice_time (
    user_id     INTEGER NOT NULL,
    session_key TEXT    NOT NULL,
    guild_id    INTEGER,
    seconds     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, session_key)
);
-- Configurações globais simples (ex.: fase da cerimônia).
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
-- Finalistas travados por categoria (snapshot das indicações ao abrir a votação).
CREATE TABLE IF NOT EXISTS finalists (
    category   TEXT    NOT NULL,
    card_id    TEXT    NOT NULL,
    card_name  TEXT    NOT NULL,
    indicacoes INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (category, card_id)
);
-- Bolão: palpite de quem vai VENCER cada categoria (não afeta o resultado).
CREATE TABLE IF NOT EXISTS bets (
    user_id    INTEGER NOT NULL,
    category   TEXT    NOT NULL,
    card_id    TEXT    NOT NULL,
    card_name  TEXT    NOT NULL,
    guild_id   INTEGER,
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, category)
);
-- Cédula final da cerimônia: 1 voto por usuário por categoria (entre finalistas).
CREATE TABLE IF NOT EXISTS final_votes (
    user_id    INTEGER NOT NULL,
    category   TEXT    NOT NULL,
    card_id    TEXT    NOT NULL,
    card_name  TEXT    NOT NULL,
    guild_id   INTEGER,
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, category)
);
"""


class Database:
    def __init__(self, path: str = DB_PATH) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self.path)
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Database.connect() não foi chamado"
        return self._db

    # ---------- votos ----------
    async def toggle_vote(
        self, user_id: int, card_id: str, card_name: str, guild_id: int | None
    ) -> bool:
        """Adiciona o voto se não existir, remove se existir.
        Retorna True se ficou votado, False se foi removido."""
        cur = await self.db.execute(
            "SELECT 1 FROM votes WHERE user_id=? AND card_id=?", (user_id, card_id)
        )
        exists = await cur.fetchone()
        if exists:
            await self.db.execute(
                "DELETE FROM votes WHERE user_id=? AND card_id=?", (user_id, card_id)
            )
            await self.db.commit()
            return False
        await self.db.execute(
            "INSERT INTO votes (user_id, card_id, card_name, guild_id) VALUES (?,?,?,?)",
            (user_id, card_id, card_name, guild_id),
        )
        await self.db.commit()
        return True

    async def count_votes(self, card_id: str) -> int:
        cur = await self.db.execute(
            "SELECT COUNT(*) FROM votes WHERE card_id=?", (card_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0

    async def ranking(self, limit: int = 10) -> list[tuple[str, str, int]]:
        cur = await self.db.execute(
            "SELECT card_id, card_name, COUNT(*) c FROM votes "
            "GROUP BY card_id ORDER BY c DESC, card_name ASC LIMIT ?",
            (limit,),
        )
        return [(r[0], r[1], r[2]) for r in await cur.fetchall()]

    # ---------- votação por categoria (cédula secreta) ----------
    async def set_category_vote(
        self,
        user_id: int,
        category: str,
        card_id: str,
        card_name: str,
        guild_id: int | None,
    ) -> None:
        """Registra/atualiza o voto do usuário NAQUELA categoria (1 por categoria)."""
        await self.db.execute(
            "INSERT INTO category_votes (user_id, category, card_id, card_name, guild_id) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id, category) DO UPDATE SET "
            "card_id=excluded.card_id, card_name=excluded.card_name, "
            "guild_id=excluded.guild_id, updated_at=datetime('now')",
            (user_id, category, card_id, card_name, guild_id),
        )
        await self.db.commit()

    async def user_category_vote(self, user_id: int, category: str) -> str | None:
        cur = await self.db.execute(
            "SELECT card_id FROM category_votes WHERE user_id=? AND category=?",
            (user_id, category),
        )
        row = await cur.fetchone()
        return row[0] if row else None

    async def category_ranking(
        self, category: str, limit: int = 25
    ) -> list[tuple[str, str, int]]:
        cur = await self.db.execute(
            "SELECT card_id, card_name, COUNT(*) c FROM category_votes "
            "WHERE category=? GROUP BY card_id ORDER BY c DESC, card_name ASC LIMIT ?",
            (category, limit),
        )
        return [(r[0], r[1], r[2]) for r in await cur.fetchall()]

    async def categories_with_votes(self) -> list[str]:
        cur = await self.db.execute(
            "SELECT DISTINCT category FROM category_votes ORDER BY category"
        )
        return [r[0] for r in await cur.fetchall()]

    async def vote_counts_per_card(self) -> dict[str, dict]:
        """{card_id: {'name','geral','categoria','indicacoes','quero'}} para o Trello.
        Só números agregados — nunca expõe quem votou/indicou."""
        out: dict[str, dict] = {}

        def slot(cid: str, name: str) -> dict:
            d = out.setdefault(
                cid,
                {"name": name, "geral": 0, "categoria": 0, "indicacoes": 0, "quero": 0},
            )
            d["name"] = name
            return d

        for tabela, chave in (
            ("votes", "geral"),
            ("category_votes", "categoria"),
            ("nominations", "indicacoes"),
            ("want_to_watch", "quero"),
        ):
            cur = await self.db.execute(
                f"SELECT card_id, card_name, COUNT(*) FROM {tabela} GROUP BY card_id"
            )
            for cid, name, c in await cur.fetchall():
                slot(cid, name)[chave] = c
        # nota média do clube (agregada)
        cur = await self.db.execute(
            "SELECT card_id, card_name, AVG(nota), COUNT(*) FROM ratings GROUP BY card_id"
        )
        for cid, name, avg, c in await cur.fetchall():
            d = slot(cid, name)
            d["nota"] = round(avg, 1)
            d["nota_n"] = c
        return out

    # ---------- notas (avaliação pós-sessão) ----------
    async def set_rating(
        self, user_id: int, card_id: str, card_name: str, nota: int, guild_id: int | None
    ) -> None:
        await self.db.execute(
            "INSERT INTO ratings (user_id, card_id, card_name, nota, guild_id) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id, card_id) DO UPDATE SET "
            "nota=excluded.nota, updated_at=datetime('now')",
            (user_id, card_id, card_name, nota, guild_id),
        )
        await self.db.commit()

    async def average_rating(self, card_id: str) -> tuple[float | None, int]:
        cur = await self.db.execute(
            "SELECT AVG(nota), COUNT(*) FROM ratings WHERE card_id=?", (card_id,)
        )
        row = await cur.fetchone()
        if not row or row[1] == 0:
            return None, 0
        return round(row[0], 1), row[1]

    async def ratings_ranking(
        self, limit: int = 15, minimo: int = 1
    ) -> list[tuple[str, str, float, int]]:
        cur = await self.db.execute(
            "SELECT card_id, card_name, ROUND(AVG(nota),1) a, COUNT(*) c FROM ratings "
            "GROUP BY card_id HAVING c>=? ORDER BY a DESC, c DESC LIMIT ?",
            (minimo, limit),
        )
        return [(r[0], r[1], r[2], r[3]) for r in await cur.fetchall()]

    # ---------- indicações do público ----------
    async def add_nomination(
        self,
        user_id: int,
        card_id: str,
        card_name: str,
        category: str,
        justificativa: str,
        guild_id: int | None,
    ) -> bool:
        """Registra/atualiza a indicação. Retorna True se foi nova, False se já existia."""
        cur = await self.db.execute(
            "SELECT 1 FROM nominations WHERE user_id=? AND card_id=? AND category=?",
            (user_id, card_id, category),
        )
        nova = await cur.fetchone() is None
        await self.db.execute(
            "INSERT INTO nominations (user_id, card_id, card_name, category, justificativa, guild_id) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(user_id, card_id, category) DO UPDATE SET "
            "justificativa=excluded.justificativa, updated_at=datetime('now')",
            (user_id, card_id, card_name, category, justificativa, guild_id),
        )
        await self.db.commit()
        return nova

    async def nomination_ranking(
        self, category: str, limit: int = 25
    ) -> list[tuple[str, str, int]]:
        cur = await self.db.execute(
            "SELECT card_id, card_name, COUNT(*) c FROM nominations "
            "WHERE category=? GROUP BY card_id ORDER BY c DESC, card_name ASC LIMIT ?",
            (category, limit),
        )
        return [(r[0], r[1], r[2]) for r in await cur.fetchall()]

    async def categories_with_nominations(self) -> list[str]:
        cur = await self.db.execute(
            "SELECT category, COUNT(*) c FROM nominations GROUP BY category ORDER BY c DESC"
        )
        return [r[0] for r in await cur.fetchall()]

    async def nomination_samples(
        self, card_id: str, category: str, limit: int = 2
    ) -> list[str]:
        cur = await self.db.execute(
            "SELECT justificativa FROM nominations "
            "WHERE card_id=? AND category=? AND COALESCE(justificativa,'')<>'' "
            "ORDER BY updated_at DESC LIMIT ?",
            (card_id, category, limit),
        )
        return [r[0] for r in await cur.fetchall()]

    async def nominations_by_user(self, user_id: int) -> list[tuple[str, str, str]]:
        cur = await self.db.execute(
            "SELECT card_name, category, COALESCE(justificativa,'') FROM nominations "
            "WHERE user_id=? ORDER BY updated_at DESC",
            (user_id,),
        )
        return [(r[0], r[1], r[2]) for r in await cur.fetchall()]

    # ---------- quero assistir logo ----------
    async def toggle_want(
        self, user_id: int, card_id: str, card_name: str, guild_id: int | None
    ) -> bool:
        cur = await self.db.execute(
            "SELECT 1 FROM want_to_watch WHERE user_id=? AND card_id=?", (user_id, card_id)
        )
        if await cur.fetchone():
            await self.db.execute(
                "DELETE FROM want_to_watch WHERE user_id=? AND card_id=?", (user_id, card_id)
            )
            await self.db.commit()
            return False
        await self.db.execute(
            "INSERT INTO want_to_watch (user_id, card_id, card_name, guild_id) VALUES (?,?,?,?)",
            (user_id, card_id, card_name, guild_id),
        )
        await self.db.commit()
        return True

    async def count_want(self, card_id: str) -> int:
        cur = await self.db.execute(
            "SELECT COUNT(*) FROM want_to_watch WHERE card_id=?", (card_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0

    # ---------- RSVP de sessões ----------
    async def set_rsvp(
        self, user_id: int, session_key: str, status: str, guild_id: int | None
    ) -> None:
        await self.db.execute(
            "INSERT INTO rsvp (user_id, session_key, status, guild_id) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id, session_key) DO UPDATE SET "
            "status=excluded.status, updated_at=datetime('now')",
            (user_id, session_key, status, guild_id),
        )
        await self.db.commit()

    async def rsvp_counts(self, session_key: str) -> dict[str, int]:
        cur = await self.db.execute(
            "SELECT status, COUNT(*) FROM rsvp WHERE session_key=? GROUP BY status",
            (session_key,),
        )
        out = {"vou": 0, "talvez": 0, "nao": 0}
        for status, c in await cur.fetchall():
            if status in out:
                out[status] = c
        return out

    async def want_ranking(self, limit: int = 15) -> list[tuple[str, str, int]]:
        cur = await self.db.execute(
            "SELECT card_id, card_name, COUNT(*) c FROM want_to_watch "
            "GROUP BY card_id ORDER BY c DESC, card_name ASC LIMIT ?",
            (limit,),
        )
        return [(r[0], r[1], r[2]) for r in await cur.fetchall()]

    # ---------- anúncios / lembretes (por servidor) ----------
    async def already_announced(self, card_id: str, event: str, guild_id: int) -> bool:
        cur = await self.db.execute(
            "SELECT 1 FROM event_log WHERE card_id=? AND event=? AND guild_id=?",
            (card_id, event, guild_id),
        )
        return await cur.fetchone() is not None

    async def mark_announced(self, card_id: str, event: str, guild_id: int) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO event_log (card_id, event, guild_id) VALUES (?,?,?)",
            (card_id, event, guild_id),
        )
        await self.db.commit()

    async def announced_count(self, event: str, guild_id: int) -> int:
        cur = await self.db.execute(
            "SELECT COUNT(*) FROM event_log WHERE event=? AND guild_id=?",
            (event, guild_id),
        )
        row = await cur.fetchone()
        return row[0] if row else 0

    # ---------- configuração por servidor ----------
    async def set_announce_channel(self, guild_id: int, channel_id: int) -> None:
        await self.db.execute(
            "INSERT INTO guild_config (guild_id, announce_channel_id) VALUES (?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET announce_channel_id=excluded.announce_channel_id",
            (guild_id, channel_id),
        )
        await self.db.commit()

    async def get_announce_channel(self, guild_id: int) -> int | None:
        cur = await self.db.execute(
            "SELECT announce_channel_id FROM guild_config WHERE guild_id=?", (guild_id,)
        )
        row = await cur.fetchone()
        return row[0] if row and row[0] else None

    async def all_announce_channels(self) -> list[tuple[int, int]]:
        cur = await self.db.execute(
            "SELECT guild_id, announce_channel_id FROM guild_config "
            "WHERE announce_channel_id IS NOT NULL"
        )
        return [(r[0], r[1]) for r in await cur.fetchall()]

    async def clear_announce_channel(self, guild_id: int) -> None:
        await self.db.execute(
            "DELETE FROM guild_config WHERE guild_id=?", (guild_id,)
        )
        await self.db.commit()

    # ---------- cerimônia (settings + finalistas + cédula final) ----------
    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        cur = await self.db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self.db.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await self.db.commit()

    async def clear_finalists(self) -> None:
        await self.db.execute("DELETE FROM finalists")
        await self.db.commit()

    async def add_finalist(
        self, category: str, card_id: str, card_name: str, indicacoes: int
    ) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO finalists (category, card_id, card_name, indicacoes) "
            "VALUES (?,?,?,?)",
            (category, card_id, card_name, indicacoes),
        )
        await self.db.commit()

    async def finalists_for(self, category: str) -> list[tuple[str, str, int]]:
        cur = await self.db.execute(
            "SELECT card_id, card_name, indicacoes FROM finalists "
            "WHERE category=? ORDER BY indicacoes DESC, card_name ASC",
            (category,),
        )
        return [(r[0], r[1], r[2]) for r in await cur.fetchall()]

    async def finalists_categories(self) -> list[str]:
        cur = await self.db.execute("SELECT DISTINCT category FROM finalists")
        return [r[0] for r in await cur.fetchall()]

    async def clear_final_votes(self) -> None:
        await self.db.execute("DELETE FROM final_votes")
        await self.db.commit()

    async def set_final_vote(
        self, user_id: int, category: str, card_id: str, card_name: str, guild_id: int | None
    ) -> None:
        await self.db.execute(
            "INSERT INTO final_votes (user_id, category, card_id, card_name, guild_id) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id, category) DO UPDATE SET "
            "card_id=excluded.card_id, card_name=excluded.card_name, updated_at=datetime('now')",
            (user_id, category, card_id, card_name, guild_id),
        )
        await self.db.commit()

    async def user_final_vote(self, user_id: int, category: str) -> str | None:
        cur = await self.db.execute(
            "SELECT card_id FROM final_votes WHERE user_id=? AND category=?",
            (user_id, category),
        )
        row = await cur.fetchone()
        return row[0] if row else None

    async def final_ranking(self, category: str, limit: int = 25) -> list[tuple[str, str, int]]:
        cur = await self.db.execute(
            "SELECT card_id, card_name, COUNT(*) c FROM final_votes "
            "WHERE category=? GROUP BY card_id ORDER BY c DESC, card_name ASC LIMIT ?",
            (category, limit),
        )
        return [(r[0], r[1], r[2]) for r in await cur.fetchall()]

    # ---------- bolão (palpites) ----------
    async def clear_bets(self) -> None:
        await self.db.execute("DELETE FROM bets")
        await self.db.commit()

    async def set_bet(
        self, user_id: int, category: str, card_id: str, card_name: str, guild_id: int | None
    ) -> None:
        await self.db.execute(
            "INSERT INTO bets (user_id, category, card_id, card_name, guild_id) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id, category) DO UPDATE SET "
            "card_id=excluded.card_id, card_name=excluded.card_name, updated_at=datetime('now')",
            (user_id, category, card_id, card_name, guild_id),
        )
        await self.db.commit()

    async def user_bet(self, user_id: int, category: str) -> str | None:
        cur = await self.db.execute(
            "SELECT card_id FROM bets WHERE user_id=? AND category=?", (user_id, category)
        )
        row = await cur.fetchone()
        return row[0] if row else None

    async def bets_by_user(self, user_id: int) -> list[tuple[str, str]]:
        cur = await self.db.execute(
            "SELECT category, card_name FROM bets WHERE user_id=? ORDER BY category",
            (user_id,),
        )
        return [(r[0], r[1]) for r in await cur.fetchall()]

    async def all_bets(self) -> list[tuple[int, str, str]]:
        cur = await self.db.execute("SELECT user_id, category, card_id FROM bets")
        return [(r[0], r[1], r[2]) for r in await cur.fetchall()]

    async def bettors_count(self) -> int:
        cur = await self.db.execute("SELECT COUNT(DISTINCT user_id) FROM bets")
        row = await cur.fetchone()
        return row[0] if row else 0

    # ---------- estatísticas do clube ----------
    async def overall_rating(self) -> tuple[float | None, int]:
        cur = await self.db.execute("SELECT AVG(nota), COUNT(*) FROM ratings")
        row = await cur.fetchone()
        if not row or not row[1]:
            return None, 0
        return round(row[0], 1), row[1]

    async def top_nominated(self, limit: int = 1) -> list[tuple[str, int]]:
        cur = await self.db.execute(
            "SELECT card_name, COUNT(*) c FROM nominations "
            "GROUP BY card_id ORDER BY c DESC LIMIT ?",
            (limit,),
        )
        return [(r[0], r[1]) for r in await cur.fetchall()]

    # ---------- tempo na call (cinema) ----------
    async def add_voice_seconds(
        self, user_id: int, session_key: str, guild_id: int | None, seconds: int
    ) -> None:
        if seconds <= 0:
            return
        await self.db.execute(
            "INSERT INTO voice_time (user_id, session_key, guild_id, seconds) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id, session_key) DO UPDATE SET seconds = seconds + excluded.seconds",
            (user_id, session_key, guild_id, seconds),
        )
        await self.db.commit()

    async def voice_points_per_user(
        self, por: int = 900, teto: int = 6
    ) -> dict[int, int]:
        """Pontos por tempo na call: +1 a cada `por` seg, com `teto` por sessão."""
        from collections import defaultdict

        pts: dict[int, int] = defaultdict(int)
        cur = await self.db.execute("SELECT user_id, seconds FROM voice_time")
        for uid, secs in await cur.fetchall():
            pts[uid] += min(secs // por, teto)
        return dict(pts)

    async def voice_seconds_per_user(self) -> dict[int, int]:
        cur = await self.db.execute(
            "SELECT user_id, SUM(seconds) FROM voice_time GROUP BY user_id"
        )
        return {uid: secs for uid, secs in await cur.fetchall()}

    # ---------- gamificação (participação agregada) ----------
    async def participation_counts(self) -> dict[int, dict[str, int]]:
        """{user_id: {chave: quantas vezes participou}} a partir de todas as tabelas."""
        from collections import defaultdict

        out: dict[int, dict[str, int]] = defaultdict(dict)
        fontes = [
            ("votes", "curtidas"),
            ("want_to_watch", "quero"),
            ("rsvp", "rsvp"),
            ("ratings", "nota"),
            ("nominations", "indicacao"),
            ("category_votes", "voto_categoria"),
            ("final_votes", "voto_final"),
            ("bets", "palpite"),
        ]
        for tabela, chave in fontes:
            cur = await self.db.execute(
                f"SELECT user_id, COUNT(*) FROM {tabela} GROUP BY user_id"
            )
            for uid, c in await cur.fetchall():
                out[uid][chave] = c
        return out
