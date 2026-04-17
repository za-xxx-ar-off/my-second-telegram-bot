import os
import json
import logging
import asyncio
import gspread
from aiohttp import web

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
SHEET_ID = os.environ["SHEET_ID"]
SERVICE_ACCOUNT_JSON = os.environ["SERVICE_ACCOUNT_JSON"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]
PORT = int(os.environ.get("PORT", 10000))

# ===== GOOGLE SHEETS =====
creds = json.loads(SERVICE_ACCOUNT_JSON)
gc = gspread.service_account_from_dict(creds)
sh = gc.open_by_key(SHEET_ID)
ws = sh.sheet1

# ===== КНОПКИ =====
LANG_KB = ReplyKeyboardMarkup(
    [[KeyboardButton("Узбекский 🇺🇿"), KeyboardButton("Русский 🇷🇺")]],
    resize_keyboard=True
)

MAIN_KB = ReplyKeyboardMarkup(
    [[KeyboardButton("Каталог"), KeyboardButton("Связаться"), KeyboardButton("Местоположение")]],
    resize_keyboard=True
)

CATALOG_KB = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Мягкая мебель"), KeyboardButton("Спальни")],
        [KeyboardButton("Кухонная гарнитура"), KeyboardButton("Видео")],
        [KeyboardButton("Назад")]
    ],
    resize_keyboard=True
)

def pager_kb():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("еще"), KeyboardButton("Назад")]],
        resize_keyboard=True
    )

COL_MAP = {
    "Мягкая мебель": "B",
    "Спальни": "C",
    "Кухонная гарнитура": "D",
    "Видео": "E"
}

# ===== ЛОГИКА =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите язык", reply_markup=LANG_KB)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_data = context.user_data

    if text in ("Узбекский 🇺🇿","Русский 🇷🇺"):
        user_data.clear()
        await update.message.reply_text("Чем я могу помочь?", reply_markup=MAIN_KB)
        return

    if text == "Каталог":
        await update.message.reply_text("Выберите категорию", reply_markup=CATALOG_KB)
        return

    if text == "Связаться":
        val = ws.acell("F1").value or "Нет контактов"
        await update.message.reply_text(val, reply_markup=MAIN_KB)
        return

    if text == "Местоположение":
        val = ws.acell("F2").value or "Нет адреса"
        await update.message.reply_text(val, reply_markup=MAIN_KB)
        return

    if text in COL_MAP:
        user_data["col"] = COL_MAP[text]
        user_data["idx"] = 1
        await send_page(update, context)
        return

    if text == "еще":
        await send_page(update, context, next_page=True)
        return

    if text == "Назад":
        await update.message.reply_text("Главное меню", reply_markup=MAIN_KB)
        return

    await update.message.reply_text("Выберите кнопку", reply_markup=MAIN_KB)


async def send_page(update: Update, context: ContextTypes.DEFAULT_TYPE, next_page=False):
    user_data = context.user_data
    col = user_data.get("col")

    if not col:
        await update.message.reply_text("Сначала выберите категорию", reply_markup=CATALOG_KB)
        return

    idx = user_data.get("idx", 1)

    if next_page:
        idx += 10

    values = ws.col_values(ord(col) - ord("A") + 1)

    photos = []
    for i in range(idx - 1, min(idx - 1 + 10, len(values))):
        url = values[i].strip()
        if url:
            photos.append(InputMediaPhoto(media=url))

    if not photos:
        await update.message.reply_text("Больше нет фото", reply_markup=CATALOG_KB)
        return

    user_data["idx"] = idx

    if len(photos) == 1:
        await update.message.reply_photo(photos[0].media, reply_markup=pager_kb())
    else:
        await update.message.reply_media_group(photos)
        await update.message.reply_text("Дальше?", reply_markup=pager_kb())


# ===== WEBHOOK =====
async def handle(request):
    data = await request.json()
    update = Update.de_json(data, request.app["bot"])
    await request.app["app"].process_update(update)
    return web.Response()


async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    await app.initialize()
    await app.start()

    webhook_url = WEBHOOK_URL + "/" + BOT_TOKEN
    await app.bot.set_webhook(webhook_url)

    print("WEBHOOK SET:", webhook_url)

    aio_app = web.Application()
    aio_app["bot"] = app.bot
    aio_app["app"] = app

    aio_app.router.add_post(f"/{BOT_TOKEN}", handle)

    runner = web.AppRunner(aio_app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print("SERVER STARTED")

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
