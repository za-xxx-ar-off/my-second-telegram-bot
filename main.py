import os
import json
import logging
from aiohttp import web
import gspread
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ['BOT_TOKEN']
SHEET_ID = os.environ['SHEET_ID']
PORT = int(os.environ.get('PORT', '8000'))
WEBHOOK_URL = os.environ['WEBHOOK_URL']  # https://<your-render-url>/

# load service account from env
sa_json = json.loads(os.environ['SERVICE_ACCOUNT_JSON'])
gc = gspread.service_account_from_dict(sa_json)
sh = gc.open_by_key(SHEET_ID)
ws = sh.sheet1

LANG_KB = ReplyKeyboardMarkup([[KeyboardButton("Узбекский 🇺🇿"), KeyboardButton("Русский 🇷🇺")]], resize_keyboard=True)
MAIN_KB = ReplyKeyboardMarkup([[KeyboardButton("Каталог"), KeyboardButton("Связаться"), KeyboardButton("Местоположение")]], resize_keyboard=True)
CATALOG_KB = ReplyKeyboardMarkup([[KeyboardButton("Мягкая мебель"), KeyboardButton("Спальни")],[KeyboardButton("Кухонная гарнитура"), KeyboardButton("Видео")],[KeyboardButton("Назад")]], resize_keyboard=True)
PAGER_KB = lambda more: ReplyKeyboardMarkup([[KeyboardButton("еще/yana"), KeyboardButton("Назад/orqaga")]], resize_keyboard=True)

# map to sheet columns (1-based)
COL_MAP = {"Мягкая мебель": "B", "Спальни": "C", "Кухонная гарнитура": "D", "Видео": "E"}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите язык", reply_markup=LANG_KB)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_data = context.user_data
    if text in ("Узбекский 🇺🇿","Русский 🇷🇺"):
        user_data.clear()
        await update.message.reply_text("Чем я могу вам помочь?", reply_markup=MAIN_KB)
        return
    if text == "Каталог":
        await update.message.reply_text("Какая мебель вам нужна?", reply_markup=CATALOG_KB)
        return
    if text == "Связаться":
        val = ws.acell('F1').value or "Контакты отсутствуют"
        await update.message.reply_text(val, reply_markup=MAIN_KB)
        return
    if text == "Местоположение":
        val = ws.acell('F2').value or "Местоположение отсутствует"
        await update.message.reply_text(val, reply_markup=MAIN_KB)
        return
    if text in COL_MAP:
        user_data['col'] = COL_MAP[text]
        user_data['idx'] = 1
        await send_page(update, context)
        return
    if text in ("еще/yana","еще","yana"):
        await send_page(update, context, next_page=True)
        return
    if text in ("Назад","orqaga","Назад/orqaga"):
        await update.message.reply_text("Чем я могу вам помочь?", reply_markup=MAIN_KB)
        return
    await update.message.reply_text("Не понял. Выберите опцию.", reply_markup=MAIN_KB)

async def send_page(update: Update, context: ContextTypes.DEFAULT_TYPE, next_page=False):
    user_data = context.user_data
    col = user_data.get('col')
    if not col:
        await update.message.reply_text("Выберите категорию.", reply_markup=CATALOG_KB)
        return
    idx = user_data.get('idx',1)
    if next_page:
        idx += 10
    # read column values starting from idx (1-based rows)
    values = ws.col_values(ord(col) - ord('A') + 1)
    photos = []
    for i in range(idx-1, min(idx-1+10, len(values))):
        url = values[i].strip()
        if url:
            photos.append(InputMediaPhoto(media=url))
    if not photos:
        await update.message.reply_text("Больше нет фотографий.", reply_markup=CATALOG_KB)
        return
    user_data['idx'] = idx
    if len(photos) == 1:
        await update.message.reply_photo(photos[0].media, reply_markup=PAGER_KB(True))
    else:
        await update.message.reply_media_group(photos)
        await update.message.reply_text("Выберите:", reply_markup=PAGER_KB(True))

async def on_startup(app):
    bot = app.bot
    await bot.set_webhook(WEBHOOK_URL + BOT_TOKEN)

async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, request.app.bot)
    await request.app.bot.process_update(update)
    return web.Response(text='OK')

def build_app():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    return application

if __name__ == "__main__":
    app = build_app()
    web_app = web.Application()
    web_app.bot = app.bot
    web_app.router.add_post(f"/{BOT_TOKEN}", handle_webhook)
    app.run_webhook(listen="0.0.0.0", port=PORT, webhook_path=f"/{BOT_TOKEN}", webhook_url=WEBHOOK_URL+BOT_TOKEN)
