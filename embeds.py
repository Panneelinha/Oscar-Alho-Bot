"""Construção dos embeds (cartões visuais) do Discord."""
from __future__ import annotations

import discord

from movies import CardExtras, LISTA_DISPONIVEL, LISTA_FORA_PREMIACAO, Movie, Sessao

COR = discord.Color.from_str("#d4af37")  # dourado, cara de Oscar


def _stars(nota: float | None) -> str:
    if nota is None:
        return ""
    cheias = int(round(nota / 2))
    return "⭐" * cheias


def movie_embed(
    mv: Movie,
    poster_url: str | None = None,
    votos: int | None = None,
    extras: CardExtras | None = None,
    nota_clube: tuple[float, int] | None = None,
) -> discord.Embed:
    titulo = mv.name
    desc_partes = []
    if mv.imdb_titulo and mv.imdb_titulo.lower() != mv.name.lower():
        desc_partes.append(f"*{mv.imdb_titulo}*")
    if mv.franquia:
        desc_partes.append(f"🎬 {mv.franquia}")
    if extras and extras.sinopse:
        desc_partes.append(f"\n> {extras.sinopse}")
    embed = discord.Embed(
        title=f"🍿 {titulo}",
        description="\n".join(desc_partes) or None,
        color=COR,
        url=mv.imdb_url or None,
    )

    if mv.imdb_nota:
        nota = f"**{mv.imdb_nota}** {_stars(mv.nota_float)}"
        if mv.imdb_avaliacoes:
            nota += f"\n{mv.imdb_avaliacoes} avaliações"
        embed.add_field(name="IMDb", value=nota, inline=True)
    if nota_clube and nota_clube[1]:
        media, n = nota_clube
        embed.add_field(
            name="🧄 Alhômetro",
            value=f"**{media}/10 dentes** {_stars(media)}\n{n} avaliação(ões)",
            inline=True,
        )
    if mv.duracao:
        embed.add_field(name="Duração", value=mv.duracao, inline=True)
    if mv.estreia:
        embed.add_field(name="Estreia", value=mv.estreia, inline=True)
    if mv.streaming:
        valor = mv.streaming
        if mv.streaming_data:
            valor += f" — {mv.streaming_data}"
        embed.add_field(name="📺 Streaming", value=valor, inline=False)

    if extras and extras.generos:
        embed.add_field(name="Gêneros", value=extras.generos, inline=True)
    if mv.labels:
        embed.add_field(name="Etiquetas", value=" ".join(f"`{l}`" for l in mv.labels), inline=True)
    if extras and extras.trailer_url:
        embed.add_field(name="▶️ Trailer", value=f"[Assistir no YouTube]({extras.trailer_url})", inline=False)

    if mv.sessao_data:
        sessao = f"📅 {mv.sessao_data}"
        if mv.sessao_programacao:
            sessao += f"\n🎬 {mv.sessao_programacao}"
        if mv.sessao_status:
            sessao += f"\n_{mv.sessao_status}_"
        embed.add_field(name="Sessão Oscar Alho", value=sessao, inline=False)

    embed.add_field(name="Categoria no Oscar Alho", value=mv.list_name, inline=False)
    if votos is not None:
        embed.add_field(name="Votos no Discord", value=f"👍 {votos}", inline=True)

    if poster_url:
        embed.set_image(url=poster_url)
    embed.set_footer(text="Oscar Alho 🧄")
    return embed


def announce_embed(
    mv: Movie, poster_url: str | None = None, extras: CardExtras | None = None
) -> discord.Embed:
    chamada = (
        "🆕 **Agora disponível no streaming!**"
        if mv.list_name == LISTA_DISPONIVEL
        else "🔜 **Em breve no streaming**"
    )
    embed = movie_embed(mv, poster_url, extras=extras)
    embed.title = f"{chamada}\n🍿 {mv.name}"
    return embed


def programacao_embed(
    sessoes: list[Sessao], disponivel: list[Movie], em_breve: list[Movie]
) -> discord.Embed:
    embed = discord.Embed(
        title="🎟️ Programação Oscar Alho",
        color=COR,
        description="As próximas sessões e o que está rolando no streaming.",
    )

    def linha(mv: Movie, com_data: bool) -> str:
        partes = [f"**{mv.name}**"]
        if mv.imdb_nota:
            partes.append(f"· {mv.imdb_nota}")
        if com_data and mv.streaming:
            quando = mv.streaming
            if mv.streaming_data:
                quando += f" {mv.streaming_data}"
            partes.append(f"· 📺 {quando}")
        elif mv.streaming:
            partes.append(f"· 📺 {mv.streaming}")
        return " ".join(partes)

    def linha_sessao(s: Sessao) -> str:
        return f"📅 `{s.quando}` — **{s.titulo}**"

    if sessoes:
        txt = "\n".join(linha_sessao(s) for s in sessoes[:10])
        embed.add_field(name="🎬 Próximas sessões", value=txt, inline=False)
    if disponivel:
        txt = "\n".join(linha(m, False) for m in disponivel[:12])
        if len(disponivel) > 12:
            txt += f"\n… e mais {len(disponivel) - 12}"
        embed.add_field(name="✅ Disponível no streaming", value=txt, inline=False)
    if em_breve:
        txt = "\n".join(linha(m, True) for m in em_breve[:12])
        if len(em_breve) > 12:
            txt += f"\n… e mais {len(em_breve) - 12}"
        embed.add_field(name="🔜 Em breve no streaming", value=txt, inline=False)
    if not sessoes and not disponivel and not em_breve:
        embed.description = "Nada na programação por enquanto."
    embed.set_footer(text="Use /filme <nome> para ver a ficha completa")
    return embed


def ranking_embed(rows: list[tuple[str, str, int]]) -> discord.Embed:
    embed = discord.Embed(title="🏆 Ranking de votos — Oscar Alho", color=COR)
    if not rows:
        embed.description = "Ainda não há votos. Use `/votar` para começar!"
        return embed
    medalhas = ["🥇", "🥈", "🥉"]
    linhas = []
    for i, (_cid, nome, c) in enumerate(rows):
        prefixo = medalhas[i] if i < 3 else f"`{i + 1}.`"
        linhas.append(f"{prefixo} **{nome}** — {c} voto(s)")
    embed.description = "\n".join(linhas)
    return embed


def category_ranking_embed(
    categoria: str, rows: list[tuple[str, str, int]], total_eleitores: int
) -> discord.Embed:
    embed = discord.Embed(title=f"🗳️ Apuração — {categoria}", color=COR)
    if not rows:
        embed.description = "Ninguém votou nesta categoria ainda. Use `/votar_categoria`."
        return embed
    total = sum(c for *_x, c in rows) or 1
    medalhas = ["🥇", "🥈", "🥉"]
    linhas = []
    for i, (_cid, nome, c) in enumerate(rows):
        prefixo = medalhas[i] if i < 3 else f"`{i + 1}.`"
        pct = round(100 * c / total)
        linhas.append(f"{prefixo} **{nome}** — {c} voto(s) ({pct}%)")
    embed.description = "\n".join(linhas)
    embed.set_footer(text=f"{total_eleitores} pessoa(s) já votaram nesta categoria • voto secreto")
    return embed


def apuracao_embed(itens: list[tuple[str, str, int]]) -> discord.Embed:
    """itens = [(categoria, lider_nome, votos)]"""
    embed = discord.Embed(
        title="🏆 Apuração geral do Oscar Alho",
        color=COR,
        description="Quem lidera em cada categoria (votos secretos dos membros).",
    )
    if not itens:
        embed.description = "Ainda não há votos em nenhuma categoria."
        return embed
    for categoria, lider, votos in itens:
        valor = f"**{lider}** — {votos} voto(s)" if lider else "_sem votos_"
        embed.add_field(name=categoria, value=valor, inline=False)
    embed.set_footer(text="Use /ranking_categoria <categoria> para o detalhe")
    return embed


def _rotulo_categoria(categoria: str) -> str:
    return "🚫 Fora da premiação" if categoria == LISTA_FORA_PREMIACAO else f"🏆 {categoria}"


def consenso_categoria_embed(
    categoria: str,
    rows: list[tuple[str, str, int]],
    amostras: dict[str, list[str]] | None = None,
) -> discord.Embed:
    fora = categoria == LISTA_FORA_PREMIACAO
    embed = discord.Embed(
        title=f"📣 Consenso do público — {_rotulo_categoria(categoria)}",
        color=COR,
        description=(
            "Filmes que o público mais quer **fora** da disputa."
            if fora
            else "Filmes mais indicados pelo público nesta categoria."
        ),
    )
    if not rows:
        embed.description = "Ninguém indicou nada aqui ainda. Use o botão **Indicar** ou `/indicar`."
        return embed
    medalhas = ["🥇", "🥈", "🥉"]
    linhas = []
    amostras = amostras or {}
    for i, (cid, nome, c) in enumerate(rows):
        prefixo = medalhas[i] if i < 3 else f"`{i + 1}.`"
        linha = f"{prefixo} **{nome}** — {c} indicação(ões)"
        for just in amostras.get(cid, [])[:1]:
            linha += f"\n   💬 _{just[:120]}_"
        linhas.append(linha)
    embed.description = "\n".join(linhas)
    embed.set_footer(text="Indicações do público (não é a categorização oficial do board)")
    return embed


def apuracao_geral_embed(
    itens: list[tuple[str, tuple[str | None, int], tuple[str | None, int]]],
    fora: tuple[str | None, int],
) -> discord.Embed:
    """Apuração unificada: cédula secreta × indicações do público, por categoria."""
    embed = discord.Embed(
        title="🏆 Apuração do Oscar Alho",
        color=COR,
        description="🗳️ Cédula secreta (`/votar_categoria`) × 📣 Indicações do público (botão Indicar).",
    )
    if not itens and not (fora and fora[0]):
        embed.description = "Ainda não há votos nem indicações. Bora movimentar! 🎬"
        return embed

    def parte(nome: str | None, n: int) -> str:
        return f"**{nome}** ({n})" if nome else "—"

    for categoria, (bn, bc), (nn, nc) in itens:
        valor = f"🗳️ {parte(bn, bc)}\n📣 {parte(nn, nc)}"
        embed.add_field(name=f"🏆 {categoria}", value=valor, inline=True)
    if fora and fora[0]:
        embed.add_field(
            name="🚫 Fora da premiação (público)",
            value=f"📣 {parte(fora[0], fora[1])}",
            inline=False,
        )
    embed.set_footer(text="🗳️ voto secreto p/ vencedor · 📣 indicações abertas")
    return embed


def consenso_geral_embed(itens: list[tuple[str, str, int]]) -> discord.Embed:
    """itens = [(categoria, lider_nome, votos)]"""
    embed = discord.Embed(
        title="📣 Consenso do público — visão geral",
        color=COR,
        description="Quem o público mais indicou em cada categoria.",
    )
    if not itens:
        embed.description = "Ainda não há indicações do público. Use o botão **Indicar** nos filmes assistidos."
        return embed
    for categoria, lider, votos in itens:
        valor = f"**{lider}** — {votos} indicação(ões)" if lider else "_sem indicações_"
        embed.add_field(name=_rotulo_categoria(categoria), value=valor, inline=False)
    embed.set_footer(text="Use /consenso <categoria> para ver o ranking completo")
    return embed


def _linha_rsvp(counts: dict[str, int]) -> str:
    return (
        f"✅ Vou: **{counts.get('vou', 0)}**  ·  "
        f"🤔 Talvez: **{counts.get('talvez', 0)}**  ·  "
        f"❌ Não: **{counts.get('nao', 0)}**"
    )


def filme_resumo_embed(mv: Movie, poster_url: str | None = None) -> discord.Embed:
    """Mini-ficha de um filme (para listar dentro de uma sessão)."""
    partes = []
    if mv.imdb_nota:
        partes.append(f"⭐ {mv.imdb_nota} {_stars(mv.nota_float)}")
    if mv.duracao:
        partes.append(f"⏱️ {mv.duracao}")
    if mv.streaming:
        # só a plataforma (sem a data de streaming, p/ não confundir com a da sessão)
        partes.append(f"📺 {mv.streaming}")
    embed = discord.Embed(
        title=f"🍿 {mv.name}",
        description=" · ".join(partes) or None,
        color=COR,
        url=mv.imdb_url or None,
    )
    if poster_url:
        embed.set_thumbnail(url=poster_url)
    return embed


def proxima_sessao_embed(
    sessao: Sessao, counts: dict[str, int], kick_url: str | None = None
) -> discord.Embed:
    embed = discord.Embed(title="🎬 Próxima sessão do Oscar Alho", color=COR)
    embed.add_field(name="Programação", value=f"**{sessao.titulo}**", inline=False)
    if sessao.epoch:
        embed.add_field(
            name="Quando",
            value=f"<t:{sessao.epoch}:F>\n⏳ <t:{sessao.epoch}:R>",
            inline=False,
        )
    elif sessao.data_str:
        embed.add_field(name="Quando", value=sessao.data_str, inline=False)
    if sessao.status:
        embed.add_field(name="Status", value=sessao.status, inline=False)
    if kick_url:
        embed.add_field(name="🔴 Transmissão", value=f"Ao vivo na Kick: {kick_url}", inline=False)
    embed.add_field(name="Presença", value=_linha_rsvp(counts), inline=False)
    embed.set_footer(text="Confirme sua presença nos botões abaixo 👇")
    return embed


def ratings_ranking_embed(rows: list[tuple[str, str, float, int]]) -> discord.Embed:
    embed = discord.Embed(title="🧄 Alhômetro — Oscar Alho", color=COR)
    if not rows:
        embed.description = "Ninguém avaliou nada ainda. Use `/nota` depois de assistir!"
        return embed
    medalhas = ["🥇", "🥈", "🥉"]
    linhas = []
    for i, (_cid, nome, media, n) in enumerate(rows):
        prefixo = medalhas[i] if i < 3 else f"`{i + 1}.`"
        linhas.append(f"{prefixo} **{nome}** — {media}/10 dentes ({n} avaliação(ões))")
    embed.description = "\n".join(linhas)
    return embed


def want_ranking_embed(rows: list[tuple[str, str, int]]) -> discord.Embed:
    embed = discord.Embed(
        title="🍿 Mais pedidos pelo público",
        color=COR,
        description="Interesse somado do site e do Discord para ajudar a curadoria a priorizar as próximas sessões.",
    )
    if not rows:
        embed.description = "Ninguém pediu nada ainda. O botão aparece em filmes não assistidos."
        return embed
    linhas = []
    for i, (_cid, nome, c) in enumerate(rows):
        prefixo = "🔥" if i == 0 else f"`{i + 1}.`"
        linhas.append(f"{prefixo} **{nome}** — {c} pedido(s)")
    embed.description = "\n".join(linhas)
    return embed


def finalistas_embed(data: list[tuple[str, list[tuple[str, int]]]]) -> discord.Embed:
    """data = [(categoria, [(nome_filme, indicacoes), ...]), ...]"""
    embed = discord.Embed(
        title="🎟️ Finalistas do Oscar Alho",
        color=COR,
        description="A votação final está **aberta**! Use **`/votar_final <categoria>`** "
        "para eleger o vencedor entre os finalistas.",
    )
    for categoria, filmes in data:
        if not filmes:
            continue
        linhas = "\n".join(f"• **{n}** ({c} indicações)" for n, c in filmes)
        embed.add_field(name=f"🏆 {categoria}", value=linhas, inline=False)
    if not embed.fields:
        embed.description = "Nenhuma categoria teve indicações suficientes."
    embed.set_footer(text="Boa sorte aos indicados! 🍿")
    return embed


def vencedores_embed(
    winners: list[tuple[str, str | None, int]], edicao: str
) -> discord.Embed:
    embed = discord.Embed(
        title=f"🏆✨ Vencedores — {edicao} ✨🏆",
        color=COR,
        description="E os vencedores do **Oscar Alho** são… 🥁",
    )
    if not winners:
        embed.description = "Não houve votos na cerimônia. 😢"
        return embed
    for categoria, nome, votos in winners:
        if nome:
            valor = f"🥇 **{nome}** — {votos} voto(s)"
        else:
            valor = "_sem votos nesta categoria_"
        embed.add_field(name=f"🎬 {categoria}", value=valor, inline=False)
    embed.set_footer(text="Obrigado a todos que votaram! 🧄🎉")
    return embed


def bolao_embed(
    ranking: list[tuple[int, int, int]], total_categorias: int, titulo: str = "🎰 Bolão do Oscar Alho"
) -> discord.Embed:
    """ranking = [(user_id, acertos, total_palpites), ...] já ordenado."""
    embed = discord.Embed(title=titulo, color=COR)
    if not ranking:
        embed.description = "Ninguém apostou ainda. Use `/palpite` durante a votação!"
        return embed
    medalhas = ["🥇", "🥈", "🥉"]
    linhas = []
    for i, (uid, acertos, _total) in enumerate(ranking[:15]):
        prefixo = medalhas[i] if i < 3 else f"`{i + 1}.`"
        linhas.append(f"{prefixo} <@{uid}> — **{acertos}/{total_categorias}** acertos")
    embed.description = "\n".join(linhas)
    embed.set_footer(text="1 ponto por vencedor cravado 🎯")
    return embed


def ranking_pontos_embed(rows: list[tuple[int, int, str]]) -> discord.Embed:
    """rows = [(user_id, pontos, nivel_nome), ...] já ordenado por pontos."""
    embed = discord.Embed(title="🌟 Ranking de pontos — Oscar Alho", color=COR)
    if not rows:
        embed.description = "Ninguém pontuou ainda. Participe (votar, indicar, avaliar…) e suba no ranking!"
        return embed
    medalhas = ["🥇", "🥈", "🥉"]
    linhas = []
    for i, (uid, pontos, nivel) in enumerate(rows[:15]):
        prefixo = medalhas[i] if i < 3 else f"`{i + 1}.`"
        linhas.append(f"{prefixo} <@{uid}> — **{pontos} pts** · {nivel}")
    embed.description = "\n".join(linhas)
    embed.set_footer(text="Use /perfil para ver seus pontos e nível")
    return embed


def estatisticas_embed(cat: dict, clube: dict) -> discord.Embed:
    embed = discord.Embed(title="📊 Estatísticas do Oscar Alho", color=COR)

    # ----- catálogo -----
    pl = cat["por_lista"]
    catalogo = [f"**{cat['total']}** filmes no board"]
    catalogo.append(
        f"🎬 Próximas sessões: {pl.get('PRÓXIMAS SESSÕES', 0)} · "
        f"📋 A assistir: {pl.get('FILMES A ASSISTIR', 0)}"
    )
    catalogo.append(
        f"✅ Streaming agora: {pl.get('STREAMING - DISPONÍVEL', 0)} · "
        f"🔜 Em breve: {pl.get('STREAMING - EM BREVE', 0)}"
    )
    if cat["media_imdb"] is not None:
        catalogo.append(f"⭐ Nota média IMDb: **{cat['media_imdb']}** {_stars(cat['media_imdb'])}")
    if cat["melhor"]:
        catalogo.append(f"🏅 Maior nota: **{cat['melhor'].name}** ({cat['melhor'].imdb_nota})")
    if cat["pior"]:
        catalogo.append(f"💩 Menor nota: **{cat['pior'].name}** ({cat['pior'].imdb_nota})")
    if cat["duracao_media_min"]:
        h, m = divmod(cat["duracao_media_min"], 60)
        catalogo.append(f"⏱️ Duração média: {h}h{m:02d}min")
    if cat["top_plataformas"]:
        plats = " · ".join(f"{nome} ({n})" for nome, n in cat["top_plataformas"])
        catalogo.append(f"📺 Plataformas: {plats}")
    embed.add_field(name="🎞️ Catálogo", value="\n".join(catalogo), inline=False)

    # ----- clube -----
    linhas = [
        f"👥 Membros ativos: **{clube['membros']}**",
        f"🔥 Participações totais: **{clube['participacoes']}**",
    ]
    if clube["nota_clube"] is not None:
        linhas.append(
            f"🧄 Alhômetro médio: **{clube['nota_clube']}/10 dentes** "
            f"{_stars(clube['nota_clube'])} ({clube['n_avaliacoes']} avaliações)"
        )
    if clube.get("top_curtido"):
        linhas.append(f"👍 Mais curtido: **{clube['top_curtido'][0]}** ({clube['top_curtido'][1]})")
    if clube.get("top_indicado"):
        linhas.append(f"🏆 Mais indicado: **{clube['top_indicado'][0]}** ({clube['top_indicado'][1]})")
    if clube.get("top_nota"):
        linhas.append(f"🌟 Líder do Alhômetro: **{clube['top_nota'][0]}** ({clube['top_nota'][1]}/10)")
    embed.add_field(name="🎟️ Clube (Discord)", value="\n".join(linhas), inline=False)

    embed.set_footer(text="Oscar Alho 🧄 • catálogo + atividade do Discord")
    return embed


def categoria_embed(nome: str, movies: list[Movie]) -> discord.Embed:
    embed = discord.Embed(title=f"📂 {nome}", color=COR)
    if not movies:
        embed.description = "Nenhum filme nesta categoria."
        return embed
    linhas = []
    for mv in movies[:25]:
        parte = f"• **{mv.name}**"
        if mv.imdb_nota:
            parte += f" — {mv.imdb_nota}"
        linhas.append(parte)
    embed.description = "\n".join(linhas)
    if len(movies) > 25:
        embed.set_footer(text=f"… e mais {len(movies) - 25}")
    return embed
