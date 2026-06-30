"""Ponte com o Telegram (somente leitura, restrita a IDs autorizados).

Reaproveita o catálogo, o banco e o cliente do Trello do bot do Discord. Roda
no mesmo processo. Ativa só se TELEGRAM_TOKEN estiver definido.
"""
from __future__ import annotations

import html
import io
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

log = logging.getLogger("oscar.telegram")


def _esc(s: object) -> str:
    return html.escape(str(s))


class TelegramBridge:
    def __init__(self, token, allowed_ids, chat_id, catalog, db, trello) -> None:
        self.allowed = set(allowed_ids)
        self.chat_id = chat_id
        self.catalog = catalog
        self.db = db
        self.trello = trello
        self.app = Application.builder().token(token).build()
        cmds = {
            "start": self.cmd_ajuda,
            "ajuda": self.cmd_ajuda,
            "help": self.cmd_ajuda,
            "id": self.cmd_id,
            "programacao": self.cmd_programacao,
            "proxima": self.cmd_proxima,
            "filme": self.cmd_filme,
            "estatisticas": self.cmd_estatisticas,
            "notas": self.cmd_notas,
        }
        for nome, handler in cmds.items():
            self.app.add_handler(CommandHandler(nome, handler))

    # ---------- ciclo de vida ----------
    async def start(self) -> None:
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
        log.info("Ponte Telegram iniciada (%d ID(s) autorizado(s)).", len(self.allowed))

    async def stop(self) -> None:
        try:
            if self.app.updater and self.app.updater.running:
                await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
        except Exception as e:  # noqa: BLE001
            log.warning("Falha ao parar a ponte Telegram: %s", e)

    # ---------- anúncios espelhados ----------
    async def anunciar(self, texto: str, foto: bytes | None = None) -> None:
        if not self.chat_id:
            return
        try:
            if foto:
                await self.app.bot.send_photo(
                    self.chat_id, photo=io.BytesIO(foto), caption=texto[:1024], parse_mode="HTML"
                )
            else:
                await self.app.bot.send_message(self.chat_id, texto[:4096], parse_mode="HTML")
        except Exception as e:  # noqa: BLE001
            log.warning("Falha ao anunciar no Telegram: %s", e)

    # ---------- utilidades ----------
    def _ok(self, update: Update) -> bool:
        u = update.effective_user
        return bool(u and u.id in self.allowed)

    async def _nego(self, update: Update) -> None:
        uid = update.effective_user.id if update.effective_user else "?"
        await update.message.reply_text(
            "🔒 Acesso restrito.\n"
            f"Seu ID do Telegram é <code>{uid}</code> — peça ao administrador para "
            "liberá-lo (TELEGRAM_ALLOWED_IDS).",
            parse_mode="HTML",
        )

    # ---------- comandos ----------
    async def cmd_id(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Mostra o ID do chat e do usuário (livre, ajuda na configuração)."""
        chat = update.effective_chat
        uid = update.effective_user.id if update.effective_user else "?"
        tipo = "grupo/canal" if chat.type in ("group", "supergroup", "channel") else "privado"
        await update.message.reply_text(
            f"🆔 <b>IDs</b>\n"
            f"Chat ({tipo}): <code>{chat.id}</code>\n"
            f"Você: <code>{uid}</code>\n\n"
            "Use o ID do chat em <b>TELEGRAM_CHAT_ID</b> (anúncios) e o seu em "
            "<b>TELEGRAM_ALLOWED_IDS</b> (acesso).",
            parse_mode="HTML",
        )

    async def cmd_ajuda(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._ok(update):
            return await self._nego(update)
        await update.message.reply_text(
            "🎬 <b>Oscar Alho — Telegram</b>\n"
            "Comandos disponíveis:\n"
            "/programacao — próximas sessões e streaming\n"
            "/proxima — a próxima sessão\n"
            "/filme &lt;nome&gt; — ficha de um filme\n"
            "/notas — filmes mais bem avaliados\n"
            "/estatisticas — panorama do clube\n\n"
            "Seu ID do Telegram: <code>%s</code>" % update.effective_user.id,
            parse_mode="HTML",
        )

    async def cmd_programacao(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._ok(update):
            return await self._nego(update)
        sessoes, disp, breve = await self.catalog.programacao()
        linhas = ["🎟️ <b>Programação Oscar Alho</b>"]
        if sessoes:
            linhas.append("\n<b>Próximas sessões:</b>")
            for s in sessoes[:10]:
                linhas.append(f"📅 {_esc(s.quando)} — {_esc(s.titulo)}")
        linhas.append(f"\n✅ No streaming: <b>{len(disp)}</b> · 🔜 Em breve: <b>{len(breve)}</b>")
        await update.message.reply_text("\n".join(linhas), parse_mode="HTML")

    async def cmd_proxima(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._ok(update):
            return await self._nego(update)
        s = await self.catalog.proxima_sessao()
        if s is None:
            await update.message.reply_text("Não há sessão agendada por enquanto. 🎬")
            return
        linhas = ["🎬 <b>Próxima sessão</b>", f"<b>{_esc(s.titulo)}</b>", f"📅 {_esc(s.quando)}"]
        if s.status:
            linhas.append(f"<i>{_esc(s.status)}</i>")
        for f in s.filmes:
            extra = f" — IMDb {_esc(f.imdb_nota)}" if f.imdb_nota else ""
            linhas.append(f"• {_esc(f.name)}{extra}")
        await update.message.reply_text("\n".join(linhas), parse_mode="HTML")

    async def cmd_filme(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._ok(update):
            return await self._nego(update)
        nome = " ".join(ctx.args).strip()
        if not nome:
            await update.message.reply_text("Use: /filme <nome do filme>")
            return
        achados = await self.catalog.buscar(nome, limite=1)
        if not achados:
            await update.message.reply_text(f"Não encontrei “{_esc(nome)}”.", parse_mode="HTML")
            return
        mv = achados[0]
        partes = [f"🍿 <b>{_esc(mv.name)}</b>"]
        if mv.imdb_titulo and mv.imdb_titulo.lower() != mv.name.lower():
            partes.append(f"<i>{_esc(mv.imdb_titulo)}</i>")
        detalhes = []
        if mv.imdb_nota:
            detalhes.append(f"⭐ {_esc(mv.imdb_nota)}")
        if mv.duracao:
            detalhes.append(f"⏱️ {_esc(mv.duracao)}")
        if mv.streaming:
            detalhes.append(f"📺 {_esc(mv.streaming)}")
        if detalhes:
            partes.append(" · ".join(detalhes))
        media, n = await self.db.average_rating(mv.id)
        if n:
            partes.append(f"🧄 Nota do clube: <b>{media}/10</b> ({n})")
        extras = await self.catalog.extras(mv.id)
        if extras.sinopse:
            partes.append(f"\n{_esc(extras.sinopse)}")
        if extras.trailer_url:
            partes.append(f"\n▶️ Trailer: {_esc(extras.trailer_url)}")
        texto = "\n".join(partes)
        poster = await self.trello.get_poster(mv.id) if mv.tem_poster else None
        if poster:
            await self.app.bot.send_photo(
                update.effective_chat.id, photo=io.BytesIO(poster[0]),
                caption=texto[:1024], parse_mode="HTML",
            )
        else:
            await update.message.reply_text(texto, parse_mode="HTML")

    async def cmd_estatisticas(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._ok(update):
            return await self._nego(update)
        s = await self.catalog.estatisticas()
        linhas = [
            "📊 <b>Estatísticas do Oscar Alho</b>",
            f"🎞️ <b>{s['total']}</b> filmes no board",
        ]
        if s["media_imdb"] is not None:
            linhas.append(f"⭐ Nota média IMDb: <b>{s['media_imdb']}</b>")
        if s["melhor"]:
            linhas.append(f"🏅 Maior nota: {_esc(s['melhor'].name)} ({_esc(s['melhor'].imdb_nota)})")
        if s["duracao_media_min"]:
            h, m = divmod(s["duracao_media_min"], 60)
            linhas.append(f"⏱️ Duração média: {h}h{m:02d}min")
        if s["top_plataformas"]:
            plats = " · ".join(f"{_esc(n)} ({c})" for n, c in s["top_plataformas"])
            linhas.append(f"📺 {plats}")
        await update.message.reply_text("\n".join(linhas), parse_mode="HTML")

    async def cmd_notas(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._ok(update):
            return await self._nego(update)
        rows = await self.db.ratings_ranking(limit=10)
        if not rows:
            await update.message.reply_text("Ainda não há notas do clube.")
            return
        linhas = ["🧄 <b>Notas do clube</b>"]
        medalhas = ["🥇", "🥈", "🥉"]
        for i, (_cid, nome, media, n) in enumerate(rows):
            pre = medalhas[i] if i < 3 else f"{i + 1}."
            linhas.append(f"{pre} {_esc(nome)} — {media}/10 ({n})")
        await update.message.reply_text("\n".join(linhas), parse_mode="HTML")
