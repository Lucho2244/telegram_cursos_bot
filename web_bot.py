# web_bot.py
# Bot de Telegram + servidor HTTP (para Web Service tipo Railway/Render)
# Requisitos: python-telegram-bot>=20.7, aiohttp>=3.9

import os
import json
import logging
import asyncio
from typing import List, Dict, Any

from aiohttp import web, ClientSession, ClientTimeout
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

# === Config ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COURSES_FILE = os.environ.get("COURSES_FILE", os.path.join(BASE_DIR, "courses.json"))
PORT = int(os.environ.get("PORT", "8080"))  # Railway/Heroku asignan PORT

# === Utilidades ===
def load_courses() -> List[Dict[str, Any]]:
    """Carga cursos desde COURSES_FILE. Devuelve [] si hay error."""
    try:
        if not os.path.exists(COURSES_FILE):
            log.error("No existe COURSES_FILE: %s", COURSES_FILE)
            return []
        with open(COURSES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        cursos = data.get("cursos", [])
        if not isinstance(cursos, list):
            log.error("Formato inválido en %s: 'cursos' no es lista", COURSES_FILE)
            return []
        log.info("Cargados %d cursos desde %s", len(cursos), COURSES_FILE)
        return cursos
    except Exception as e:
        log.exception("Error leyendo %s: %s", COURSES_FILE, e)
        return []

def build_keyboard(cursos: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Genera teclado para listado de cursos. Si no hay, muestra Reintentar."""
    if not cursos:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Reintentar", callback_data="RELOAD")]
        ])
    rows = []
    for c in cursos:
        title = c.get("titulo", "Curso")
        cid = str(c.get("id", "") or "")
        # callback_data máx 64 chars → recortar por seguridad
        cb = ("CUR|" + cid)[:64]
        rows.append([InlineKeyboardButton(f"📘 {title}", callback_data=cb)])
    return InlineKeyboardMarkup(rows)

def fmt_course(c: Dict[str, Any]) -> str:
    """Texto bonito para la ficha del curso."""
    titulo = c.get("titulo", "Curso")
    desc = c.get("descripcion_corta", "")
    dur = c.get("duracion", "")
    precio = c.get("precio", "")
    parts = [f"*{titulo}*"]
    if desc:
        parts.append(desc)
    if dur:
        parts.append(f"Duración: {dur}")
    if precio:
        parts.append(f"Precio: {precio}")
    return "\n".join(parts).strip()

async def safe_edit(q, text: str, markup: InlineKeyboardMarkup):
    """Edita mensaje sin romper si el contenido es igual."""
    try:
        await q.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            # Intentá sólo actualizar el teclado
            try:
                await q.edit_message_reply_markup(reply_markup=markup)
            except BadRequest:
                pass
        else:
            raise

# === Handlers del bot ===
async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cursos = load_courses()
    kb = build_keyboard(cursos)
    msg = "📚 *Cursos disponibles:*" if cursos else "⚠️ No hay cursos válidos. Revisá courses.json y probá Reintentar."
    if update.message:
        await update.message.reply_text(msg, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    else:
        # Por seguridad si viniera de otro tipo de update
        await ctx.bot.send_message(chat_id=update.effective_chat.id, text=msg, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def cursos_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await start_cmd(update, ctx)

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    log.info("Callback: %s", data)

    if data == "RELOAD":
        cursos = load_courses()
        kb = build_keyboard(cursos)
        msg = "📚 *Cursos disponibles:*" if cursos else "⚠️ No hay cursos válidos. Revisá courses.json y probá Reintentar."
        await safe_edit(q, msg, kb)
        return

    if data.startswith("CUR|"):
        course_id = data.split("|", 1)[1]
        cursos = load_courses()
        c = next((x for x in cursos if str(x.get("id", "")) == course_id), None)
        if not c:
            await safe_edit(q, "No encontré ese curso. Probá /cursos.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver", callback_data="RELOAD")]]))
            return
        buttons = []
        link = c.get("link_inscripcion")
        if link:
            buttons.append([InlineKeyboardButton("📝 Inscribirme", url=link)])
        buttons.append([InlineKeyboardButton("⬅️ Volver", callback_data="RELOAD")])
        await safe_edit(q, fmt_course(c), InlineKeyboardMarkup(buttons))
        return

async def fallback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Usá /start o /cursos para ver el listado.")

# === Arranque del bot (long polling) con anti-conflictos ===
async def run_bot():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN")

    # 🔒 Limpieza proactiva: liberar cualquier sesión previa de getUpdates
    try:
        timeout = ClientTimeout(total=10)
        async with ClientSession(timeout=timeout) as s:
            await s.get(f"https://api.telegram.org/bot{token}/deleteWebhook")
            await s.get(f"https://api.telegram.org/bot{token}/close")
        log.info("deleteWebhook + close ejecutados")
    except Exception as e:
        log.warning("No se pudo ejecutar deleteWebhook/close: %s", e)

    app = ApplicationBuilder().token(token).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("cursos", cursos_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback))

    # (Opcional) handler global de errores
    async def error_handler(update, context):
        log.exception("Excepción no capturada: %s", context.error)
    app.add_error_handler(error_handler)

    # Iniciar y hacer polling en paralelo al HTTP
    await app.initialize()
    await app.start()
    log.info("Bot de Telegram iniciado (long polling).")
    await app.updater.start_polling(drop_pending_updates=True)
    await asyncio.Event().wait()

# === Servidor HTTP (health checks) ===
async def run_http():
    async def health(_):
        # info útil para diagnosticar
        exists = os.path.exists(COURSES_FILE)
        count = len(load_courses()) if exists else 0
        return web.Response(text=f"ok | courses={count}")

    http = web.Application()
    http.router.add_get("/", health)
    http.router.add_get("/health", health)

    runner = web.AppRunner(http)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    log.info(f"HTTP listo en :{PORT}")
    await asyncio.Event().wait()

# === Entrypoint: bot + http en paralelo ===
async def main():
    await asyncio.gather(run_bot(), run_http())

if __name__ == "__main__":
    asyncio.run(main())
