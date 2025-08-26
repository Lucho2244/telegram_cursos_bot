# web_bot.py
import os, json, logging, asyncio
from aiohttp import web
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

COURSES_FILE = "courses.json"

def load_courses():
    try:
        with open(COURSES_FILE, encoding="utf-8") as f:
            return json.load(f).get("cursos", [])
    except Exception as e:
        log.error("No pude leer %s: %s", COURSES_FILE, e)
        return []

def build_keyboard(cursos):
    if not cursos:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Reintentar", callback_data="RELOAD")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton(c.get("titulo","Curso"), callback_data=f"CUR|{c.get('id','')}")] for c in cursos])

def fmt(c):
    txt = f"*{c.get('titulo','Curso')}*\n{c.get('descripcion_corta','')}\n"
    if c.get("duracion"): txt += f"Duración: {c['duracion']}\n"
    if c.get("precio"): txt += f"Precio: {c['precio']}"
    return txt.strip()

async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = build_keyboard(load_courses())
    await update.message.reply_text("📚 *Cursos disponibles:*", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def cursos_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await start_cmd(update, ctx)

async def btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if data == "RELOAD":
        kb = build_keyboard(load_courses())
        await q.edit_message_text("📚 *Cursos disponibles:*", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        return
    if data.startswith("CUR|"):
        course_id = data.split("|",1)[1]
        c = next((x for x in load_courses() if str(x.get("id","")) == course_id), None)
        if not c:
            await q.edit_message_text("No encontré ese curso. Probá /cursos.")
            return
        buttons = []
        if c.get("link_inscripcion"):
            buttons.append([InlineKeyboardButton("📝 Inscribirme", url=c["link_inscripcion"])])
        buttons.append([InlineKeyboardButton("⬅️ Volver", callback_data="RELOAD")])
        await q.edit_message_text(fmt(c), parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))

async def fallback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Usá /start o /cursos para ver el listado.")

async def run_bot():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token: raise RuntimeError("Falta TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("cursos", cursos_cmd))
    app.add_handler(CallbackQueryHandler(btn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback))
    await app.initialize()
    await app.start()
    log.info("Bot de Telegram iniciado (long polling).")
    # run_polling como tarea
    await app.updater.start_polling(drop_pending_updates=True)
    # mantener la tarea viva
    await asyncio.Event().wait()

async def run_http():
    async def health(_): return web.Response(text="ok")
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    port = int(os.environ.get("PORT", "8080"))
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port); await site.start()
    log.info(f"HTTP listo en :{port}")
    await asyncio.Event().wait()

async def main():
    await asyncio.gather(run_bot(), run_http())

if __name__ == "__main__":
    asyncio.run(main())
