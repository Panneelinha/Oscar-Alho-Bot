"""Testes offline do parser e dos embeds usando dados reais do board OSCAR ALHO.
Rode com:  python test_parser.py   (não precisa de token nem de internet)."""
from __future__ import annotations

import embeds
from movies import Movie, Sessao, _parse_sessao_dt

# Cards reais extraídos do board OSCAR ALHO (campo desc fiel ao Trello).
FIXTURES = [
    {
        "card": {
            "id": "0PDzY8Ps01",
            "name": "Extermínio: O Templo dos Ossos",
            "due": "2026-04-03T00:00:00.000Z",
            "badges": {"votes": 0, "attachments": 1},
            "shortUrl": "https://trello.com/c/0PDzY8Ps",
            "desc": (
                "Estreia: 13/01\n"
                "Streaming: Max — 03/04/2026\n"
                "Franquia: Saga 28 Days Later (filme 4 de 4)\n"
                "Duração: 1h49min\n\n"
                "## IMDb\n"
                "**Nota atual:** 7,2/10 (111.051 avaliações)\n"
                "**Estreia:** 16/01/2026\n"
                "**Título no IMDb:** [28 Years Later: The Bone Temple](https://www.imdb.com/title/tt32141377/)\n"
                "**Consulta:** 27/06/2026 (BRT)"
            ),
        },
        "list": "STREAMING - DISPONÍVEL",
        "espera": {
            "streaming": "Max",
            "streaming_data": "03/04/2026",
            "franquia": "Saga 28 Days Later (filme 4 de 4)",
            "duracao": "1h49min",
            "imdb_nota": "7,2/10",
            "imdb_avaliacoes": "111.051",
            "imdb_titulo": "28 Years Later: The Bone Temple",
            "imdb_url": "https://www.imdb.com/title/tt32141377/",
        },
    },
    {
        "card": {
            "id": "convite01",
            "name": "O Convite",
            "due": None,
            "badges": {"votes": 0},
            "shortUrl": "https://trello.com/c/abc",
            "desc": "Estreia: 24/01\nDuração: 1h47min",
        },
        "list": "FILMES A ASSISTIR",
        "espera": {"estreia": "24/01", "duracao": "1h47min", "streaming": None, "imdb_nota": None},
    },
    {
        "card": {
            "id": "socorro01",
            "name": "Socorro!",
            "due": None,
            "badges": {"votes": 0},
            "shortUrl": "https://trello.com/c/def",
            "desc": (
                "## IMDb\n"
                "**Nota atual:** 6,7/10 (127.828 avaliações)\n"
                "**Estreia:** 30/01/2026\n"
                "**Título no IMDb:** [Send Help](https://www.imdb.com/title/tt8036976/)\n"
                "**Consulta:** 27/06/2026 (BRT)"
            ),
        },
        "list": "FILME ASSISTIDOS",
        "espera": {"imdb_nota": "6,7/10", "imdb_titulo": "Send Help", "streaming": None},
    },
    {
        "card": {"id": "vazio01", "name": "Você ou eu?", "due": None, "badges": {}, "desc": ""},
        "list": "FILME ASSISTIDOS",
        "espera": {"imdb_nota": None, "streaming": None, "duracao": None},
    },
]


def main() -> None:
    movies = []
    falhas = 0
    for fx in FIXTURES:
        mv = Movie.from_card(fx["card"], fx["list"])
        movies.append(mv)
        for campo, esperado in fx["espera"].items():
            obtido = getattr(mv, campo)
            ok = obtido == esperado
            falhas += not ok
            marca = "✓" if ok else "✗ FALHOU"
            print(f"  [{marca}] {mv.name} · {campo} = {obtido!r}" + ("" if ok else f" (esperado {esperado!r})"))

    # nota_float e estrelas
    extermínio = movies[0]
    assert extermínio.nota_float == 7.2, extermínio.nota_float
    assert extermínio.due is not None

    # busca/normalização
    assert extermínio.matches("templo dos ossos")
    assert extermínio.matches("bone temple")  # casa pelo título IMDb

    # parsing da sessão do clube (formato real do board)
    card_sessao = {
        "id": "ses1", "name": "Killer Whale", "due": "2026-01-16T00:00:00.000Z",
        "badges": {}, "shortUrl": "u",
        "desc": (
            "Estreia: 16/01\nStreaming: Netflix — 16/01/2026\n\n"
            "## Sessão Oscar Alho\n"
            "**Agendada para:** 03/07/2026, 21h00\n"
            "**Programação:** Killer Whale + Passageiro do Mal\n"
            "**Status:** Agendada — aguarda realização\n"
        ),
    }
    ms = Movie.from_card(card_sessao, "PRÓXIMAS SESSÕES")
    assert ms.sessao_data == "03/07/2026, 21h00", ms.sessao_data
    assert ms.sessao_programacao == "Killer Whale + Passageiro do Mal"
    assert ms.sessao_dt is not None and (ms.sessao_dt.day, ms.sessao_dt.month, ms.sessao_dt.hour) == (3, 7, 21), ms.sessao_dt
    print(f"  [✓] sessão parseada: {ms.sessao_dt}  ({ms.sessao_programacao})")
    sess = Sessao(ms.sessao_data, ms.sessao_dt, ms.sessao_programacao, ms.sessao_status, [ms])
    assert sess.quando == "03/07 · 21h", sess.quando

    # embeds não podem estourar exceção
    embeds.movie_embed(ms, "http://x/poster.jpg", votos=3)
    embeds.programacao_embed([sess], [extermínio], [movies[1]])
    embeds.ranking_embed([(extermínio.id, extermínio.name, 5)])
    embeds.categoria_embed("ATOR PRINCIPAL", movies)

    print("\nResumo:", "TODOS OS TESTES PASSARAM ✅" if falhas == 0 else f"{falhas} FALHA(S) ❌")
    raise SystemExit(1 if falhas else 0)


if __name__ == "__main__":
    main()
