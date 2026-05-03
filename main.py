import os
import json
import logging
import asyncio
import gspread
from aiohttp import web

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
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

# ===== GOOGLE DRIVE LINK =====
def convert_drive_url(url: str) -> str:
    if "drive.google.com" in url:
        try:
            file_id = url.split("/d/")[1].split("/")[0]
            return f"https://drive.google.com/uc?export=download&id={file_id}"
        except:
            return url
    return url

# ===== ТЕКСТЫ =====
TEXTS = {
    "ru": {
        "choose_lang": "Выберите язык",
        "menu": "Чем я могу помочь?",
        "catalog": "Каталог",
        "contact": "Связаться",
        "location": "Местоположение",
        "more": "еще",
        "back": "Назад",
        "next": "Дальше?",
        "no_photo": "Фото закончились, выбрать другую категорию?",
        "no_contacts": "Нет контактов",
        "no_address": "Нет адреса",
        "choose_btn": "Выберите кнопку",
        "yes": "Да",
        "no": "Нет",

        "kitchen": "Кухонные гарнитуры",
        "bedroom": "Спальни",
        "other": "Остальная мебель",
        "soft": "Мягкая мебель",
        "video": "Видео"
    },

    "uz": {
        "choose_lang": "Tilni tanlang",
        "menu": "Qanday yordam bera olaman?",
        "catalog": "Katalog",
        "contact": "Bog‘lanish",
        "location": "Joylashuv",
        "more": "yana",
        "back": "orqaga",
        "next": "Davom etamizmi?",
        "no_photo": "Rasmlar tugadi, boshqa bo‘lim tanlaysizmi?",
        "no_contacts": "Kontakt yo‘q",
        "no_address": "Manzil yo‘q",
        "choose_btn": "Tugmani tanlang",
        "yes": "Ha",
        "no": "Yo‘q",

        "kitchen": "Oshxona garniturlari",
        "bedroom": "Yotoqxonalar",
        "other": "Boshqa mebellar",
        "soft": "Yumshoq mebel",
        "video": "Video"
    }
}

# ===== КНОПКИ =====
def get_main_kb(lang):
    t = TEXTS[lang]
    return ReplyKeyboardMarkup(
        [[KeyboardButton(t["catalog"]), KeyboardButton(t["contact"]), KeyboardButton(t["location"])]],
        resize_keyboard=True
    )

def get_catalog_kb(lang):
    t = TEXTS[lang]
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(t["kitchen"]), KeyboardButton(t["bedroom"])],
            [KeyboardButton(t["other"]), KeyboardButton(t["soft"])],
            [KeyboardButton(t["video"])],
            [KeyboardButton(t["back"])]
        ],
        resize_keyboard=True
    )

def get_pager_kb(lang):
    t = TEXTS[lang]
    return ReplyKeyboardMarkup(
        [[KeyboardButton(t["more"]), KeyboardButton(t["back"])]],
        resize_keyboard=True
    )

def get_yesno_kb(lang):
    t = TEXTS[lang]
    return ReplyKeyboardMarkup(
        [[KeyboardButton(t["yes"]), KeyboardButton(t["no"])]],
        resize_keyboard=True
    )

LANG_KB = ReplyKeyboardMarkup(
    [[KeyboardButton("Узбекский 🇺🇿"), KeyboardButton("Русский 🇷🇺")]],
    resize_keyboard=True
)

# ===== HELPERS =====
def get_lang(user_data):
    return user_data.get("lang", "ru")

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите язык", reply_markup=LANG_KB)

# ===== MAIN TEXT HANDLER =====
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_data = context.user_data

    # язык
    if text == "Русский 🇷🇺":
        user_data.clear()
        user_data["lang"] = "ru"
        await update.message.reply_text(TEXTS["ru"]["menu"], reply_markup=get_main_kb("ru"))
        return

    if text == "Узбекский 🇺🇿":
        user_data.clear()
        user_data["lang"] = "uz"
        await update.message.reply_text(TEXTS["uz"]["menu"], reply_markup=get_main_kb("uz"))
        return

    lang = get_lang(user_data)
    t = TEXTS[lang]

    # да / нет
    if text == t["yes"]:
        await update.message.reply_text(t["catalog"], reply_markup=get_catalog_kb(lang))
        return

    if text == t["no"]:
        await update.message.reply_text(t["menu"], reply_markup=get_main_kb(lang))
        return

    # каталог
    if text == t["catalog"]:
        await update.message.reply_text(t["catalog"], reply_markup=get_catalog_kb(lang))
        return

    # категории
    if text == t["kitchen"]:
        user_data["col"] = "A"
        user_data["type"] = "photo"
        user_data["idx"] = 1
        await send_page(update, context)
        return

    if text == t["bedroom"]:
        user_data["col"] = "B"
        user_data["type"] = "photo"
        user_data["idx"] = 1
        await send_page(update, context)
        return

    if text == t["other"]:
        user_data["col"] = "C"
        user_data["type"] = "photo"
        user_data["idx"] = 1
        await send_page(update, context)
        return

    if text == t["video"]:
        user_data["col"] = "D"
        user_data["type"] = "video"
        user_data["idx"] = 1
        await send_page(update, context)
        return

    if text == t["soft"]:
        user_data["col"] = "E"
        user_data["type"] = "photo"
        user_data["idx"] = 1
        await send_page(update, context)
        return

    # контакты
    if text == t["contact"]:
        val = ws.acell("F1").value or t["no_contacts"]
        await update.message.reply_text(val, reply_markup=get_main_kb(lang))
        return

    # локация
    if text == t["location"]:
        val = ws.acell("G1").value or t["no_address"]
        await update.message.reply_text(val, reply_markup=get_main_kb(lang))
        return

    # ещё
    if text == t["more"]:
        await send_page(update, context, next_page=True)
        return

    # назад
    if text == t["back"]:
        await update.message.reply_text(t["menu"], reply_markup=get_main_kb(lang))
        return

    await update.message.reply_text(t["choose_btn"], reply_markup=get_main_kb(lang))

# ===== SEND PAGE =====
async def send_page(update: Update, context: ContextTypes.DEFAULT_TYPE, next_page=False):
    user_data = context.user_data
    lang = get_lang(user_data)
    t = TEXTS[lang]

    col = user_data.get("col")
    media_type = user_data.get("type", "photo")

    if not col:
        await update.message.reply_text(t["catalog"], reply_markup=get_catalog_kb(lang))
        return

    idx = user_data.get("idx", 1)

    if next_page:
        idx += 10

    values = ws.col_values(ord(col) - ord("A") + 1)

    items = []
    for i in range(idx - 1, min(idx - 1 + 10, len(values))):
        raw_url = values[i].strip()
        if raw_url:
            items.append(convert_drive_url(raw_url))

    if not items:
        await update.message.reply_text(t["no_photo"], reply_markup=get_yesno_kb(lang))
        return

    user_data["idx"] = idx

    for i, url in enumerate(items):
        last = i == len(items) - 1

        if media_type == "video":
            if last:
                await update.message.reply_video(url, reply_markup=get_pager_kb(lang))
            else:
                await update.message.reply_video(url)
        else:
            if last:
                await update.message.reply_photo(url, reply_markup=get_pager_kb(lang))
            else:
                await update.message.reply_photo(url)

        await asyncio.sleep(0.3)

# ===== WEBHOOK =====
async def handle(request):
    data = await request.json()
    update = Update.de_json(data, request.app["bot"])
    await request.app["app"].process_update(update)
    return web.Response()

# ===== MAIN =====
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
