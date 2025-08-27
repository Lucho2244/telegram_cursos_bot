# web_bot.py
# Bot de Telegram + servidor HTTP (para Web Service tipo Railway/Render con plan free)
# Requisitos: python-telegram-bot>=20.7, aiohttp>=3.9

import os
import json
import logging
import asyncio
from typing import List, Dict, Any

from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

# === Rutas y config ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COURSES_FILE = os.environ.get("COURSES_FILE", os.path.join(BASE_DIR, "courses.json"))
PORT = int(os.environ.get("PORT", "8080"))  # Railway/Heroku asignan PORT

# === Utilidades de cursos ===
def load_courses() -> List[Dict[str, Any]]:
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
    if not cursos:
        # Si no hay cursos, mostramos "Reintentar" para recargar luego del deploy
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Reintentar", callback_data="RELOAD")]
        ])
    buttons = [
        [InlineKeyboardButton(c.get("titulo", "Curso"), callback_data=f"CUR|{c.get('id','')}")]
        for c in cursos
    ]
    return InlineKeyboardMarkup(buttons)

def fmt_course(c: Dict[str, Any]) -> str:
    titulo = c.get("titulo", "Curso")
    desc = c.get("descripcion_corta", "")
    dur = c.get("duracion", "")
    precio = c.get("precio", "")
    txt = f"*{titulo}*\n{desc}\n"
    if dur:
        txt += f"Duración: {dur}\n"
    if precio:
        txt += f"Precio: {precio}"
    return txt.strip()

# === Handlers del bot ===
async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cursos = load_courses()
    kb = build_keyboard(cursos)
    await update.message.reply_text(
        "📚 *Cursos disponibles:*",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN
    )

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
        await q.edit_message_text(
            "📚 *Cursos disponibles:*",
            reply_markup=kb,
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if data.startswith("CUR|"):
        course_id = data.split("|", 1)[1]
        c = next((x for x in load_courses() if str(x.get("id", "")) == course_id), None)
        if not c:
            await q.edit_message_text("No encontré ese curso. Probá /cursos.")
            return
        buttons = []
        link = c.get("link_inscripcion")
        if link:
            buttons.append([InlineKeyboardButton("📝 Inscribirme", url=link)])
        buttons.append([InlineKeyboardButton("⬅️ Volver", callback_data="RELOAD")])
        await q.edit_message_text(
            fmt_course(c),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

async def fallback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Usá /start o /cursos para ver el listado.")

# === Corrida del bot (long polling) ===
async def run_bot():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("cursos", cursos_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback))

    await app.initialize()
    await app.start()
    log.info("Bot de Telegram iniciado (long polling).")

    # Inicia getUpdates (polling) y deja la tarea viva
    await app.updater.start_polling(drop_pending_updates=True)
    await asyncio.Event().wait()

# === Servidor HTTP para health checks ===
async def run_http():
    async def health(_):
        return web.Response(text="ok")

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
