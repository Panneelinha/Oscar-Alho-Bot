"""Modelo de filme e parser do `desc` dos cards do Trello.

O `desc` segue um padrão como:

    Estreia: 13/01
    Streaming: Max — 03/04/2026
    Franquia: Saga 28 Days Later (filme 4 de 4)
    Duração: 1h49min

    ## IMDb
    **Nota atual:** 7,2/10 (111.051 avaliações)
    **Estreia:** 16/01/2026
    **Título no IMDb:** [28 Years Later: The Bone Temple](https://www.imdb.com/title/tt32141377/)
    **Consulta:** 27/06/2026 (BRT)

Nem todo card tem todos os campos — o parser é tolerante a ausências.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ----- Nomes das listas do board OSCAR ALHO -----
LISTA_PROXIMAS_SESSOES = "PRÓXIMAS SESSÕES"   # programação do clube (com datas)
LISTA_DISPONIVEL = "STREAMING - DISPONÍVEL"
LISTA_EM_BREVE = "STREAMING - EM BREVE"
LISTA_A_ASSISTIR = "FILMES A ASSISTIR"
LISTA_ASSISTIDOS = "ASSISTIDOS — PENDENTE DE CATEGORIZAÇÃO"
LISTA_FORA_PREMIACAO = "FORA DA PREMIAÇÃO"

# Listas que representam as categorias de indicação do "Oscar Alho".
CATEGORIAS_PREMIACAO = [
    "FILME NACIONAL",
    "FILME INTERNACIONAL",
    "ATOR PRINCIPAL",
    "ATRIZ PRINCIPAL",
    "ATOR COADJUVANTE",
    "ATRIZ COADJUVANTE",
    "DIREÇÃO",
    "ROTEIRO",
    "FIGURINO E MAQUIAGEM",
    "DESIGN DE PRODUÇÃO",
    "EFEITOS PRÁTICOS",
    "EFEITOS DIGITAIS",
    "INVERSÃO NARRATIVA",
    "SOLUÇÃO NARRATIVA",
    "ARCO DE PROTAGOSNSTA",
    "ARCO DE ANTAGONISTA",
    "LACRAÇÃO PONTUAL",
    "LACRAÇÃO GERAL",
    "PRÊMIO DESONORÁRIO",
]

# Opções que o público pode escolher ao "indicar" um filme assistido:
# as categorias de prêmio + a opção de tirar da disputa.
OPCOES_INDICACAO = CATEGORIAS_PREMIACAO + [LISTA_FORA_PREMIACAO]

# Listas em que o filme AINDA NÃO foi assistido pelo clube.
LISTAS_NAO_ASSISTIDAS = {
    LISTA_PROXIMAS_SESSOES,
    LISTA_DISPONIVEL,
    LISTA_EM_BREVE,
    LISTA_A_ASSISTIR,
}


def foi_assistido(list_name: str) -> bool:
    """True se o filme já foi assistido (pode receber indicação a prêmio)."""
    return list_name not in LISTAS_NAO_ASSISTIDAS


_RE_STREAMING = re.compile(r"^Streaming:\s*(.+?)(?:\s*[—–-]\s*(\d{2}/\d{2}/\d{4}))?\s*$", re.M)
_RE_FRANQUIA = re.compile(r"^Franquia:\s*(.+)$", re.M)
_RE_DURACAO = re.compile(r"^Duração:\s*(.+)$", re.M)
_RE_ESTREIA = re.compile(r"^Estreia:\s*(.+)$", re.M)
_RE_NOTA = re.compile(r"\*\*Nota atual:\*\*\s*([0-9.,]+/10)\s*(?:\(([\d.\s]+)\s*avalia)?", re.M)
_RE_IMDB_TITULO = re.compile(r"\*\*T[íi]tulo no IMDb:\*\*\s*\[([^\]]+)\]\(([^)]+)\)", re.M)
# Seção "## Sessão Oscar Alho" dos cards de PRÓXIMAS SESSÕES.
_RE_SESSAO_DATA = re.compile(r"\*\*Agendada para:\*\*\s*(.+)", re.M)
_RE_SESSAO_PROG = re.compile(r"\*\*Programação:\*\*\s*(.+)", re.M)
_RE_SESSAO_STATUS = re.compile(r"\*\*Status:\*\*\s*(.+)", re.M)
_RE_DATA_BR = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_RE_HORA = re.compile(r"(\d{1,2})h(\d{2})?")


def _parse_sessao_dt(texto: str | None) -> datetime | None:
    """De 'Agendada para: 03/07/2026, 21h00' tira um datetime (naive, hora local)."""
    if not texto:
        return None
    m = _RE_DATA_BR.search(texto)
    if not m:
        return None
    dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hh = mm = 0
    if (h := _RE_HORA.search(texto)):
        hh, mm = int(h.group(1)), int(h.group(2) or 0)
    try:
        return datetime(ano, mes, dia, hh, mm)
    except ValueError:
        return None


def _norm(s: str) -> str:
    """Normaliza para busca: minúsculas, sem acentos, sem pontuação extra."""
    import unicodedata

    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def canonical_movie_key(movie: "Movie") -> str:
    """Identidade estável compartilhada pelas cópias do mesmo filme no Trello."""
    imdb_match = re.search(r"/title/(tt\d+)", movie.imdb_url or "", re.I)
    if imdb_match:
        return f"imdb:{imdb_match.group(1).lower()}"
    title = _norm(movie.imdb_titulo or movie.name)
    slug = re.sub(r"\s+", "-", title).strip("-")
    return f"title:{slug or movie.id.lower()}"


@dataclass
class Movie:
    id: str
    name: str
    desc: str
    list_name: str
    url: str
    due: datetime | None = None
    votes_trello: int = 0
    # Campos extraídos do desc:
    estreia: str | None = None
    streaming: str | None = None
    streaming_data: str | None = None
    franquia: str | None = None
    duracao: str | None = None
    imdb_nota: str | None = None
    imdb_avaliacoes: str | None = None
    imdb_titulo: str | None = None
    imdb_url: str | None = None
    labels: list[str] = field(default_factory=list)   # etiquetas (BETA, MACUMBA…)
    tem_poster: bool = False                           # tem imagem anexada?
    # Sessão do clube (apenas cards de PRÓXIMAS SESSÕES):
    sessao_data: str | None = None       # ex.: "03/07/2026, 21h00"
    sessao_programacao: str | None = None
    sessao_status: str | None = None
    sessao_dt: datetime | None = None    # data/hora parseada (para ordenar)

    @classmethod
    def from_card(cls, card: dict, list_name: str) -> "Movie":
        desc = card.get("desc") or ""
        badges = card.get("badges") or {}

        due = None
        if card.get("due"):
            try:
                due = datetime.fromisoformat(card["due"].replace("Z", "+00:00"))
            except ValueError:
                due = None

        streaming = streaming_data = None
        if (m := _RE_STREAMING.search(desc)):
            streaming = m.group(1).strip() or None
            streaming_data = (m.group(2) or "").strip() or None

        nota = avaliacoes = None
        if (m := _RE_NOTA.search(desc)):
            nota = m.group(1)
            avaliacoes = (m.group(2) or "").strip() or None

        imdb_titulo = imdb_url = None
        if (m := _RE_IMDB_TITULO.search(desc)):
            imdb_titulo, imdb_url = m.group(1).strip(), m.group(2).strip()

        def grab(rx):
            m = rx.search(desc)
            return m.group(1).strip() if m else None

        sessao_data = grab(_RE_SESSAO_DATA)

        return cls(
            id=card["id"],
            name=card.get("name", "(sem nome)"),
            desc=desc,
            list_name=list_name,
            url=card.get("shortUrl") or card.get("url") or "",
            due=due,
            votes_trello=int(badges.get("votes") or 0),
            estreia=grab(_RE_ESTREIA),
            streaming=streaming,
            streaming_data=streaming_data,
            franquia=grab(_RE_FRANQUIA),
            duracao=grab(_RE_DURACAO),
            imdb_nota=nota,
            imdb_avaliacoes=avaliacoes,
            imdb_titulo=imdb_titulo,
            imdb_url=imdb_url,
            labels=[l.get("name") for l in (card.get("labels") or []) if l.get("name")],
            tem_poster=bool(badges.get("attachments")),
            sessao_data=sessao_data,
            sessao_programacao=grab(_RE_SESSAO_PROG),
            sessao_status=grab(_RE_SESSAO_STATUS),
            sessao_dt=_parse_sessao_dt(sessao_data),
        )

    # ---- ajudantes de exibição ----
    @property
    def search_key(self) -> str:
        return _norm(self.name)

    @property
    def nota_float(self) -> float | None:
        if not self.imdb_nota:
            return None
        try:
            return float(self.imdb_nota.split("/")[0].replace(",", "."))
        except ValueError:
            return None

    def matches(self, query: str) -> bool:
        q = _norm(query)
        return q in self.search_key or (
            self.imdb_titulo is not None and q in _norm(self.imdb_titulo)
        )


@dataclass
class Sessao:
    """Uma sessão do clube — pode ter mais de um filme (sessão dupla)."""
    data_str: str | None          # texto cru, ex.: "03/07/2026, 21h00"
    dt: datetime | None           # data/hora parseada (para ordenar)
    programacao: str | None       # ex.: "Killer Whale + Passageiro do Mal"
    status: str | None
    filmes: list[Movie]

    @property
    def quando(self) -> str:
        if self.dt:
            txt = self.dt.strftime("%d/%m")
            if self.dt.hour or self.dt.minute:
                txt += f" · {self.dt.hour}h" + (f"{self.dt.minute:02d}" if self.dt.minute else "")
            return txt
        return self.data_str or "a definir"

    @property
    def titulo(self) -> str:
        return self.programacao or " + ".join(f.name for f in self.filmes)

    @property
    def chave(self) -> str | None:
        """Identificador estável da sessão (para RSVP), baseado na data/hora."""
        return self.dt.strftime("%Y%m%d%H%M") if self.dt else None

    @property
    def epoch(self) -> int | None:
        """Timestamp Unix (hora de São Paulo) para contagem regressiva no Discord."""
        if not self.dt:
            return None
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo("America/Sao_Paulo")
        except Exception:
            tz = timezone.utc
        return int(self.dt.replace(tzinfo=tz).timestamp())


_RE_YT = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/watch\?\S+|youtu\.be/[\w\-]+)", re.I
)
_RE_DASH = re.compile(r"\s[—–]\s")  # separador "Rótulo — conteúdo"
_RE_FONTE = re.compile(r"\n?(?:Fonte:|Verificado em:)", re.I)
_RE_ROTULO_FONTE = re.compile(r"^[A-Za-zÀ-ÿ0-9 ]{1,20}:\s*")


@dataclass
class CardExtras:
    """Infos extraídas dos comentários do card (sinopse, trailer, gêneros)."""
    sinopse: str | None = None
    trailer_url: str | None = None
    generos: str | None = None


def _limpar_sinopse(txt: str) -> str | None:
    corpo = _RE_FONTE.split(txt)[0]                  # corta em "Fonte:/Verificado em:"
    partes = _RE_DASH.split(corpo, maxsplit=1)        # tira o rótulo "Sinopse … —"
    corpo = (partes[1] if len(partes) > 1 else corpo).strip()
    corpo = _RE_ROTULO_FONTE.sub("", corpo)           # tira "IMDb:" do começo
    return corpo.strip() or None


def parse_comentarios(textos: list[str]) -> CardExtras:
    """Lê os comentários (mais recentes primeiro) e pega o 1º de cada tipo."""
    extras = CardExtras()
    for txt in textos:
        baixo = txt.lstrip().lower()
        if extras.sinopse is None and baixo.startswith("sinopse"):
            extras.sinopse = _limpar_sinopse(txt)
        elif extras.trailer_url is None and baixo.startswith("trailer"):
            if (m := _RE_YT.search(txt)):
                extras.trailer_url = m.group(0)
        elif extras.generos is None and baixo.startswith(
            ("categorias:", "categoria:", "gênero", "genero")
        ):
            if ":" in txt:
                extras.generos = txt.split(":", 1)[1].strip().rstrip(".") or None
        if extras.sinopse and extras.trailer_url and extras.generos:
            break
    return extras


def now_utc() -> datetime:
    return datetime.now(timezone.utc)

