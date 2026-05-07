import os
import json
import asyncio
import logging
import gspread
import io

from datetime import datetime
from aiohttp import web

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)

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

BOT_TOKEN = os.environ.get("BOT_TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")
SERVICE_ACCOUNT_JSON = os.environ.get("SERVICE_ACCOUNT_JSON")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 10000))

ADMIN_IDS = [
    int(x) for x in os.environ.get("ADMIN_IDS", "").split(",")
    if x.strip()
]

# DRIVE FOLDERS
FOLDERS = {
    "A": os.environ.get("DRIVE_FOLDER_KITCHEN"),
    "B": os.environ.get("DRIVE_FOLDER_BEDROOM"),
    "C": os.environ.get("DRIVE_FOLDER_OTHER"),
    "D": os.environ.get("DRIVE_FOLDER_VIDEO"),
    "E": os.environ.get("DRIVE_FOLDER_SOFT"),
}

if not all([BOT_TOKEN, SHEET_ID, SERVICE_ACCOUNT_JSON, WEBHOOK_URL]):
    raise ValueError("❌ Missing ENV variables")

# ======================================================
# GOOGLE
# ======================================================

from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]

credentials = Credentials.from_service_account_info(
    creds,
    scopes=SCOPES
)

gc = gspread.authorize(credentials)

sh = gc.open_by_key(SHEET_ID)
ws = sh.sheet1

drive_service = build(
    "drive",
    "v3",
    credentials=credentials,
    cache_discovery=False
)

# ======================================================
# CACHE
# ======================================================

CACHE = {}

# ======================================================
# TEXTS
# ======================================================

TEXTS = {
    "ru": {
        "menu": "Чем я могу помочь?",
        "catalog": "Каталог",
        "contact": "Связаться",
        "location": "Местоположение",

        "more": "Еще",
        "back": "Назад",

        "next": "Еще или Назад?",
        "finished": "Фото закончились, выбрать другую категорию?",

        "yes": "Да",
        "no": "Нет",

        "admin": "Админ панель",

        "upload_ok": "✅ Загружено",
        "send_file": "Отправьте фото или видео",

        "kitchen": "Кухонные гарнитуры",
        "bedroom": "Спальни",
        "other": "Остальная мебель",
        "soft": "Мягкая мебель",
        "video": "Видео"
    },

    "uz": {
        "menu": "Qanday yordam bera olaman?",
        "catalog": "Katalog",
        "contact": "Bog‘lanish",
        "location": "Joylashuv",

        "more": "Yana",
        "back": "Orqaga",

        "next": "Yana yoki Orqaga?",
        "finished": "Rasmlar tugadi, boshqa bo‘lim tanlaysizmi?",

        "yes": "Ha",
        "no": "Yo‘q",

        "admin": "Admin panel",

        "upload_ok": "✅ Yuklandi",
        "send_file": "Rasm yoki video yuboring",

        "kitchen": "Oshxona garniturlari",
        "bedroom": "Yotoqxonalar",
        "other": "Boshqa mebellar",
        "soft": "Yumshoq mebel",
        "video": "Video"
    }
}

# ======================================================
# HELPERS
# ======================================================

def get_lang(user_data):
    return user_data.get("lang", "ru")


def is_admin(update):
    return update.effective_user.id in ADMIN_IDS


def convert_drive_url(url: str) -> str:
    if "drive.google.com" in url:
        try:
            if "/file/d/" in url:
                file_id = url.split("/d/")[1].split("/")[0]
            elif "id=" in url:
                file_id = url.split("id=")[1].split("&")[0]
            else:
                return url

            return f"https://drive.google.com/uc?export=download&id={file_id}"

        except:
            return url

    return url

# ======================================================
# KEYBOARDS
# ======================================================

def kb_main(lang, admin=False):
    t = TEXTS[lang]

    kb = [
        [
            KeyboardButton(t["catalog"]),
            KeyboardButton(t["contact"]),
            KeyboardButton(t["location"])
        ]
    ]

    if admin:
        kb.append([KeyboardButton(t["admin"])])

    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


def kb_catalog(lang):
    t = TEXTS[lang]

    return ReplyKeyboardMarkup([
        [t["kitchen"], t["bedroom"]],
        [t["other"], t["soft"]],
        [t["video"]],
        [t["back"]]
    ], resize_keyboard=True)


def kb_more(lang):
    t = TEXTS[lang]

    return ReplyKeyboardMarkup([
        [t["more"], t["back"]]
    ], resize_keyboard=True)


def kb_yesno(lang):
    t = TEXTS[lang]

    return ReplyKeyboardMarkup([
        [t["yes"], t["no"]]
    ], resize_keyboard=True)


def kb_admin(lang):
    t = TEXTS[lang]

    return ReplyKeyboardMarkup([
        [t["kitchen"], t["bedroom"]],
        [t["other"], t["soft"]],
        [t["video"]],
        [t["back"]]
    ], resize_keyboard=True)

# ======================================================
# LOG
# ======================================================

def write_log(update, category, file_type):
    user = update.effective_user

    username = f"@{user.username}" if user.username else "no_username"

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    text = f"{now} | {username} ({user.id}) | {category} | {file_type}"

    next_row = len(ws.col_values(10)) + 1

    ws.update_cell(next_row, 10, text)

# ======================================================
# DRIVE UPLOAD
# ======================================================

def upload_to_drive(file_bytes, filename, mime_type, folder_id):
    file_metadata = {
        "name": filename,
        "parents": [folder_id]
    }

    media = MediaIoBaseUpload(
        io.BytesIO(file_bytes),
        mimetype=mime_type
    )

    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    file_id = file.get("id")

    drive_service.permissions().create(
        fileId=file_id,
        body={
            "type": "anyone",
            "role": "reader"
        }
    ).execute()

    return f"https://drive.google.com/file/d/{file_id}/view"

# ======================================================
# START
# ======================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выберите язык",
        reply_markup=ReplyKeyboardMarkup(
            [["Узбекский 🇺🇿", "Русский 🇷🇺"]],
            resize_keyboard=True
        )
    )

# ======================================================
# CACHE SEND
# ======================================================

async def send_cached(bot_method, chat_id, url, is_video=False):
    if url in CACHE:
        return await bot_method(chat_id, CACHE[url])

    msg = await bot_method(chat_id, url)

    try:
        if is_video:
            CACHE[url] = msg.video.file_id
        else:
            CACHE[url] = msg.photo[-1].file_id
    except:
        pass

    return msg

# ======================================================
# SEND PAGE
# ======================================================

async def send_page(update, context, next_page=False):
    u = context.user_data

    lang = get_lang(u)

    t = TEXTS[lang]

    col = u.get("col")
    typ = u.get("type", "photo")

    idx = u.get("idx", 1)

    if next_page:
        idx += 10

    values = ws.col_values(ord(col) - 64)

    items = []

    for i in range(idx - 1, min(idx + 9, len(values))):
        url = values[i].strip()

        if url:
            items.append(convert_drive_url(url))

    if not items:
        await update.message.reply_text(
            t["finished"],
            reply_markup=kb_yesno(lang)
        )
        return

    u["idx"] = idx

    await update.message.reply_text(
        "...",
        reply_markup=ReplyKeyboardRemove()
    )

    for url in items:
        try:
            if typ == "video":
                await send_cached(
                    context.bot.send_video,
                    update.effective_chat.id,
                    url,
                    True
                )
            else:
                await send_cached(
                    context.bot.send_photo,
                    update.effective_chat.id,
                    url
                )

            await asyncio.sleep(0.3)

        except Exception as e:
            print("SEND ERROR:", e)

    if idx + 10 <= len(values):
        await update.message.reply_text(
            t["next"],
            reply_markup=kb_more(lang)
        )
    else:
        await update.message.reply_text(
            t["finished"],
            reply_markup=kb_yesno(lang)
        )

# ======================================================
# TEXT HANDLER
# ======================================================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    u = context.user_data

    # LANGUAGE

    if text == "Русский 🇷🇺":
        u.clear()
        u["lang"] = "ru"

        await update.message.reply_text(
            TEXTS["ru"]["menu"],
            reply_markup=kb_main("ru", is_admin(update))
        )
        return

    if text == "Узбекский 🇺🇿":
        u.clear()
        u["lang"] = "uz"

        await update.message.reply_text(
            TEXTS["uz"]["menu"],
            reply_markup=kb_main("uz", is_admin(update))
        )
        return

    lang = get_lang(u)

    t = TEXTS[lang]

    # ADMIN PANEL

    if text == t["admin"] and is_admin(update):
        u["admin"] = True

        await update.message.reply_text(
            "ADMIN MODE",
            reply_markup=kb_admin(lang)
        )
        return

    # BACK

    if text == t["back"]:
        u["admin"] = False

        await update.message.reply_text(
            t["menu"],
            reply_markup=kb_main(lang, is_admin(update))
        )
        return

    # MAIN

    if text == t["catalog"]:
        await update.message.reply_text(
            t["catalog"],
            reply_markup=kb_catalog(lang)
        )
        return

    if text == t["contact"]:
        await update.message.reply_text(
            ws.acell("F1").value or "-",
            reply_markup=kb_main(lang, is_admin(update))
        )
        return

    if text == t["location"]:
        await update.message.reply_text(
            ws.acell("G1").value or "-",
            reply_markup=kb_main(lang, is_admin(update))
        )
        return

    if text == t["yes"]:
        await update.message.reply_text(
            t["catalog"],
            reply_markup=kb_catalog(lang)
        )
        return

    if text == t["no"]:
        await update.message.reply_text(
            t["menu"],
            reply_markup=kb_main(lang, is_admin(update))
        )
        return

    if text == t["more"]:
        await send_page(update, context, True)
        return

    # CATEGORY MAP

    mapping = {
        t["kitchen"]: ("A", "photo"),
        t["bedroom"]: ("B", "photo"),
        t["other"]: ("C", "photo"),
        t["video"]: ("D", "video"),
        t["soft"]: ("E", "photo"),
    }

    # ADMIN CATEGORY SELECT

    if u.get("admin") and text in mapping:
        col, typ = mapping[text]

        u["upload_col"] = col
        u["upload_type"] = typ

        await update.message.reply_text(
            t["send_file"],
            reply_markup=ReplyKeyboardRemove()
        )

        return

    # USER CATEGORY SELECT

    if text in mapping:
        col, typ = mapping[text]

        u["col"] = col
        u["type"] = typ
        u["idx"] = 1

        await send_page(update, context)

# ======================================================
# MEDIA HANDLER
# ======================================================

async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = context.user_data

    if not u.get("admin"):
        return

    col = u.get("upload_col")

    if not col:
        return

    file = None
    mime = "image/jpeg"
    file_type = "photo"

    if update.message.photo:
        file = await update.message.photo[-1].get_file()

    elif update.message.video:
        file = await update.message.video.get_file()
        mime = "video/mp4"
        file_type = "video"

    else:
        return

    data = await file.download_as_bytearray()

    folder_id = FOLDERS.get(col)

    link = upload_to_drive(
        data,
        "file",
        mime,
        folder_id
    )

    col_index = ord(col) - 64

    next_row = len(ws.col_values(col_index)) + 1

    ws.update_cell(next_row, col_index, link)

    write_log(update, col, file_type)

    await update.message.reply_text(
        TEXTS[get_lang(u)]["upload_ok"]
    )

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

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler
        )
    )

    app.add_handler(
        MessageHandler(
            filters.PHOTO | filters.VIDEO,
            media_handler
        )
    )

    await app.initialize()
    await app.start()

    webhook = WEBHOOK_URL.rstrip("/") + "/" + BOT_TOKEN

    print("WEBHOOK:", webhook)

    await app.bot.set_webhook(webhook)

    aio = web.Application()

    aio["bot"] = app.bot
    aio["app"] = app

    aio.router.add_post(f"/{BOT_TOKEN}", handle)

    runner = web.AppRunner(aio)

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        PORT
    )

    await site.start()

    print("SERVER STARTED")

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
