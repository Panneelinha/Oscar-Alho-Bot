"""Camada de serviço: lê o board pelo TrelloClient, monta objetos Movie e
oferece consultas (programação, busca, categorias) com um cache curto."""
from __future__ import annotations

import re
import time
from collections import Counter
from datetime import datetime

from movies import (
    CATEGORIAS_PREMIACAO,
    LISTA_A_ASSISTIR,
    LISTA_ASSISTIDOS,
    LISTA_DISPONIVEL,
    LISTA_EM_BREVE,
    LISTA_PROXIMAS_SESSOES,
    CardExtras,
    Movie,
    Sessao,
    canonical_movie_key,
    parse_comentarios,
)

_RE_DUR = re.compile(r"(\d+)\s*h(?:\s*(\d+)\s*min)?")


def _plataforma_valida(p: str | None) -> bool:
    if not p:
        return False
    p = p.strip()
    if not p or p[0] in "—–-":
        return False
    baixo = p.lower()
    return not any(x in baixo for x in ("verificado", "disponí", "a definir", "?"))
from trello_client import TrelloClient

CACHE_TTL = 60  # segundos


class Catalog:
    def __init__(self, trello: TrelloClient) -> None:
        self.trello = trello
        self._by_list: dict[str, list[Movie]] = {}
        self._by_id: dict[str, Movie] = {}
        self._list_ids: dict[str, str] = {}
        self._loaded_at = 0.0

    def invalidate(self) -> None:
        """Força recarregar do Trello na próxima consulta (após criar/mover card)."""
        self._loaded_at = 0.0

    async def refresh(self, force: bool = False) -> None:
        if not force and (time.time() - self._loaded_at) < CACHE_TTL and self._by_id:
            return
        lists = await self.trello.get_lists_with_cards()
        by_list: dict[str, list[Movie]] = {}
        by_id: dict[str, Movie] = {}
        list_ids: dict[str, str] = {}
        for lst in sorted(lists, key=lambda l: l.get("pos", 0)):
            name = lst.get("name", "")
            list_ids[name] = lst.get("id")
            movies = [Movie.from_card(c, name) for c in lst.get("cards", [])]
            by_list[name] = movies
            for mv in movies:
                # um filme pode aparecer em mais de uma lista; mantemos o 1º id visto
                by_id.setdefault(mv.id, mv)
        self._by_list, self._by_id, self._list_ids = by_list, by_id, list_ids
        self._loaded_at = time.time()

    async def list_id(self, name: str) -> str | None:
        await self.refresh()
        alvo = name.strip().lower()
        for n, i in self._list_ids.items():
            if n.lower() == alvo:
                return i
        for n, i in self._list_ids.items():
            if alvo in n.lower():
                return i
        return None

    async def sessoes(self) -> list[Sessao]:
        await self.refresh()
        return self._sessoes()

    async def proxima_sessao(self) -> Sessao | None:
        await self.refresh()
        sessoes = self._sessoes()
        agora = datetime.now()
        futuras = [s for s in sessoes if s.dt and s.dt >= agora]
        if futuras:
            return futuras[0]
        return sessoes[0] if sessoes else None

    # ---------- consultas ----------
    def _sessoes(self) -> list[Sessao]:
        """Agrupa os cards de PRÓXIMAS SESSÕES por sessão (data) e ordena por data."""
        grupos: dict[str, list[Movie]] = {}
        for mv in self._by_list.get(LISTA_PROXIMAS_SESSOES, []):
            chave = mv.sessao_data or f"__{mv.id}"  # cards sem data: cada um sozinho
            grupos.setdefault(chave, []).append(mv)
        sessoes = [
            Sessao(
                data_str=filmes[0].sessao_data,
                dt=filmes[0].sessao_dt,
                programacao=filmes[0].sessao_programacao,
                status=filmes[0].sessao_status,
                filmes=filmes,
            )
            for filmes in grupos.values()
        ]
        sessoes.sort(key=lambda s: (s.dt is None, s.dt or datetime.max))
        return sessoes

    async def programacao(self) -> tuple[list[Sessao], list[Movie], list[Movie]]:
        """Retorna (próximas sessões agrupadas, disponível no streaming, em breve)."""
        await self.refresh()
        disponivel = list(self._by_list.get(LISTA_DISPONIVEL, []))
        em_breve = sorted(
            self._by_list.get(LISTA_EM_BREVE, []),
            key=lambda m: (m.due is None, m.due),
        )
        return self._sessoes(), disponivel, em_breve

    async def categoria(self, nome: str) -> list[Movie]:
        await self.refresh()
        # casa por nome exato ou aproximado (case-insensitive)
        alvo = nome.strip().lower()
        for lname, movies in self._by_list.items():
            if lname.lower() == alvo:
                return movies
        for lname, movies in self._by_list.items():
            if alvo in lname.lower():
                return movies
        return []

    async def nomes_listas(self) -> list[str]:
        await self.refresh()
        return list(self._by_list.keys())

    async def categorias_premiacao(self) -> list[str]:
        await self.refresh()
        return [c for c in CATEGORIAS_PREMIACAO if self._by_list.get(c)]

    async def buscar(self, query: str, limite: int = 25) -> list[Movie]:
        await self.refresh()
        vistos: set[str] = set()
        out: list[Movie] = []
        for mv in self._by_id.values():
            if mv.matches(query) and mv.id not in vistos:
                vistos.add(mv.id)
                out.append(mv)
                if len(out) >= limite:
                    break
        return out

    async def por_id(self, card_id: str) -> Movie | None:
        await self.refresh()
        return self._by_id.get(card_id)

    async def por_chave_canonica(self, key: str) -> list[Movie]:
        await self.refresh()
        return [mv for mv in self._by_id.values() if canonical_movie_key(mv) == key]

    async def extras(self, card_id: str) -> CardExtras:
        """Sinopse/trailer/gêneros lidos dos comentários do card (sob demanda)."""
        try:
            textos = await self.trello.get_card_comments(card_id)
        except Exception:
            return CardExtras()
        return parse_comentarios(textos)

    async def todos(self) -> list[Movie]:
        await self.refresh()
        return list(self._by_id.values())

    async def estatisticas(self) -> dict:
        await self.refresh()
        movies = list(self._by_id.values())
        notas = [(m, m.nota_float) for m in movies if m.nota_float is not None]
        media_imdb = round(sum(n for _m, n in notas) / len(notas), 1) if notas else None
        melhor = max(notas, key=lambda x: x[1])[0] if notas else None
        pior = min(notas, key=lambda x: x[1])[0] if notas else None
        plataformas = Counter(
            m.streaming.strip() for m in movies if _plataforma_valida(m.streaming)
        )
        duracoes = []
        for m in movies:
            if m.duracao and (mm := _RE_DUR.search(m.duracao)):
                duracoes.append(int(mm.group(1)) * 60 + int(mm.group(2) or 0))
        dur_media = round(sum(duracoes) / len(duracoes)) if duracoes else None
        return {
            "total": len(movies),
            "por_lista": {
                nome: len(self._by_list.get(nome, []))
                for nome in (
                    LISTA_PROXIMAS_SESSOES,
                    LISTA_DISPONIVEL,
                    LISTA_EM_BREVE,
                    LISTA_A_ASSISTIR,
                    LISTA_ASSISTIDOS,
                )
            },
            "media_imdb": media_imdb,
            "melhor": melhor,
            "pior": pior,
            "top_plataformas": plataformas.most_common(3),
            "duracao_media_min": dur_media,
        }


