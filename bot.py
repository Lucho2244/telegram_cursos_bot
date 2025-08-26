#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Bot de Telegram para cursos (usa python-telegram-bot v20+)
import os, json, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_courses():
    with open("courses.json", encoding="utf-8") as f:
        return json.load(f)["cursos"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursos = load_courses()
    buttons = [[InlineKeyboardButton(c["titulo"], callback_data=c["id"])] for c in cursos]
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("📚 Cursos disponibles:", reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cursos = load_courses()
    c = next((x for x in cursos if x["id"] == query.data), None)
    if c:
        text = f"*{c['titulo']}*\n{c['descripcion_corta']}\nDuración: {c['duracion']}\nPrecio: {c['precio']}"
        kb = [[InlineKeyboardButton("📝 Inscribirme", url=c["link_inscripcion"])]]
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("⚠️ Falta TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    logger.info("Bot iniciado...")
    app.run_polling()

if __name__ == "__main__":
    main()
