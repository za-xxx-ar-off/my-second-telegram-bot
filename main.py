import os
import json
import asyncio
import logging
import gspread

from datetime import datetime
from aiohttp import web
from google.oauth2.service_account import Credentials

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

logging.basicConfig(level=logging.INFO)

print("BOT STARTING...")

# ======================================================
# ENV
# ======================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]
SHEET_ID = os.environ["SHEET_ID"]
SERVICE_ACCOUNT_JSON = os.environ["SERVICE_ACCOUNT_JSON"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]
PORT = int(os.environ.get("PORT", 10000))

ADMIN_IDS = [
    int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()
]

if not all([BOT_TOKEN, SHEET_ID, SERVICE_ACCOUNT_JSON, WEBHOOK_URL]):
    raise ValueError("Missing ENV variables")

# ======================================================
# GOOGLE SHEETS
# ======================================================

creds_dict = json.loads(SERVICE_ACCOUNT_JSON)

credentials = Credentials.from_service_account_info(
    creds_dict,
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets"
    ]
)

gc = gspread.authorize(credentials)
ws = gc.open_by_key(SHEET_ID).sheet1

# ======================================================
# TEXTS
# ======================================================

TEXTS = {
    "ru": {
        "menu": "Меню",
        "catalog": "Каталог",
        "contact": "Связаться",
        "location": "Локация",
        "admin": "Админ",
        "back": "Назад",
        "upload_ok": "Загружено"
    }
}

# ======================================================
# HELPERS
# ======================================================

def lang(u):
    return u.get("lang", "ru")

def is_admin(update):
    return update.effective_user.id in ADMIN_IDS

def log(update, category, file_type):
    user = update.effective_user
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    username = f"@{user.username}" if user.username else "no_username"

    text = f"{now} | {username} ({user.id}) | {category} | {file_type}"

    next_row = len(ws.col_values(10)) + 1
    ws.update_cell(next_row, 10, text)

# ======================================================
# KEYBOARDS
# ======================================================

def kb_main(admin=False):
    kb = [["Каталог", "Связаться", "Локация"]]
    if admin:
        kb.append(["Админ"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def kb_catalog():
    return ReplyKeyboardMarkup([
        ["Кухня", "Спальня"],
        ["Другое", "Мягкая"],
        ["Видео"],
        ["Назад"]
    ], resize_keyboard=True)

def kb_admin():
    return ReplyKeyboardMarkup([
        ["Кухня", "Спальня"],
        ["Другое", "Мягкая"],
        ["Видео"],
        ["Назад"]
    ], resize_keyboard=True)

# ======================================================
# START
# ======================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Меню", reply_markup=kb_main(is_admin(update)))

# ======================================================
# TEXT HANDLER
# ======================================================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    u = context.user_data

    if text == "Админ" and is_admin(update):
        u["admin"] = True
        await update.message.reply_text("Админ режим", reply_markup=kb_admin())
        return

    if text == "Назад":
        u["admin"] = False
        await update.message.reply_text("Меню", reply_markup=kb_main(is_admin(update)))
        return

    if text == "Каталог":
        await update.message.reply_text("Каталог", reply_markup=kb_catalog())
        return

    mapping = {
        "Кухня": "A",
        "Спальня": "B",
        "Другое": "C",
        "Видео": "D",
        "Мягкая": "E"
    }

    if text in mapping:
        u["col"] = mapping[text]
        await update.message.reply_text("Отправь фото/видео")
        return

# ======================================================
# MEDIA HANDLER (file_id ONLY)
# ======================================================

async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = context.user_data

    if not u.get("admin"):
        return

    col = u.get("col")
    if not col:
        return

    file_id = None
    file_type = None

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = "photo"

    elif update.message.video:
        file_id = update.message.video.file_id
        file_type = "video"

    else:
        return

    col_index = ord(col) - 64
    next_row = len(ws.col_values(col_index)) + 1

    ws.update_cell(next_row, col_index, file_id)

    log(update, col, file_type)

    await update.message.reply_text("Готово", reply_markup=kb_admin())

# ======================================================
# WEBHOOK
# ======================================================

async def handle(request):
    data = await request.json()
    update = Update.de_json(data, request.app["bot"])

    asyncio.create_task(
        request.app["app"].process_update(update)
    )

    return web.Response()

# ======================================================
# MAIN
# ======================================================

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, media_handler))

    await app.initialize()
    await app.start()

    webhook = WEBHOOK_URL.rstrip("/") + "/" + BOT_TOKEN
    await app.bot.set_webhook(webhook)

    aio = web.Application()
    aio["bot"] = app.bot
    aio["app"] = app

    aio.router.add_post(f"/{BOT_TOKEN}", handle)

    aio.router.add_get("/", lambda r: web.Response(text="OK"))

    runner = web.AppRunner(aio)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print("SERVER STARTED")

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
