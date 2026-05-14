import os
import json
import asyncio
import gspread

from aiohttp import web
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

print("BOT STARTING...")

# ======================================================
# ENV
# ======================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]
SHEET_ID = os.environ["SHEET_ID"]
SERVICE_ACCOUNT_JSON = os.environ["SERVICE_ACCOUNT_JSON"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]

PORT = int(os.environ.get("PORT", 10000))

# ======================================================
# GOOGLE SHEETS
# ======================================================

creds = json.loads(SERVICE_ACCOUNT_JSON)

gc = gspread.service_account_from_dict(creds)
ws = gc.open_by_key(SHEET_ID).sheet1

# ======================================================
# TEXTS
# ======================================================

TEXTS = {
    "ru": {
        "menu": "Меню",
        "catalog": "Каталог",
        "back": "Назад",
        "finished": "Файлы закончились"
    }
}

# ======================================================
# KEYBOARDS
# ======================================================

def kb_main():
    return ReplyKeyboardMarkup(
        [["Каталог"]],
        resize_keyboard=True
    )


def kb_catalog():
    return ReplyKeyboardMarkup([
        ["Кухня", "Спальня"],
        ["Другое", "Мягкая мебель"],
        ["Видео"],
        ["Назад"]
    ], resize_keyboard=True)

# ======================================================
# HELPERS
# ======================================================

def col_map():
    return {
        "Кухня": "A",
        "Спальня": "B",
        "Другое": "C",
        "Видео": "D",
        "Мягкая мебель": "E"
    }


def get_col_values(col):
    return ws.col_values(ord(col) - 64)


def convert(url: str):
    if "drive.google.com" in url and "/file/d/" in url:
        try:
            file_id = url.split("/d/")[1].split("/")[0]
            return f"https://drive.google.com/uc?export=download&id={file_id}"
        except:
            return url
    return url

# ======================================================
# START
# ======================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Меню", reply_markup=kb_main())

# ======================================================
# SEND PAGE
# ======================================================

async def send_category(update, context):
    u = context.user_data

    col = u.get("col")
    if not col:
        return

    values = get_col_values(col)

    if not values:
        await update.message.reply_text("Пусто")
        return

    for url in values:
        try:
            url = convert(url)

            if col == "D":
                await context.bot.send_video(update.effective_chat.id, url)
            else:
                await context.bot.send_photo(update.effective_chat.id, url)

            await asyncio.sleep(0.2)

        except Exception as e:
            print("SEND ERROR:", e)

# ======================================================
# TEXT HANDLER
# ======================================================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    u = context.user_data

    if text == "Каталог":
        await update.message.reply_text("Каталог", reply_markup=kb_catalog())
        return

    if text == "Назад":
        u.clear()
        await update.message.reply_text("Меню", reply_markup=kb_main())
        return

    mapping = col_map()

    if text in mapping:
        u["col"] = mapping[text]
        await send_category(update, context)
        return

# ======================================================
# WEBHOOK
# ======================================================

async def handle(request):
    data = await request.json()
    update = Update.de_json(data, request.app["bot"])

    asyncio.create_task(
        request.app["app"].process_update(update)
    )

    return web.Response(text="OK")

# ======================================================
# MAIN
# ======================================================

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

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
