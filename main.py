import os
import json
import io
import asyncio
import logging
import gspread

from datetime import datetime
from aiohttp import web

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from telegram import (
    Update,
    ReplyKeyboardMarkup,
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
    int(x)
    for x in os.environ.get("ADMIN_IDS", "").split(",")
    if x.strip()
]

FOLDERS = {
    "A": os.environ.get("DRIVE_FOLDER_KITCHEN"),
    "B": os.environ.get("DRIVE_FOLDER_BEDROOM"),
    "C": os.environ.get("DRIVE_FOLDER_OTHER"),
    "D": os.environ.get("DRIVE_FOLDER_VIDEO"),
    "E": os.environ.get("DRIVE_FOLDER_SOFT"),
}

if not all([
    BOT_TOKEN,
    SHEET_ID,
    SERVICE_ACCOUNT_JSON,
    WEBHOOK_URL
]):
    raise ValueError("❌ Missing ENV variables")

# ======================================================
# GOOGLE
# ======================================================

creds = json.loads(SERVICE_ACCOUNT_JSON)

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]

credentials = Credentials.from_service_account_info(
    creds,
    scopes=SCOPES
)

gc = gspread.authorize(credentials)

ws = gc.open_by_key(SHEET_ID).sheet1

drive_service = build(
    "drive",
    "v3",
    credentials=credentials,
    cache_discovery=False
)

# ======================================================
# HELPERS
# ======================================================

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


def log(update, category, file_type):
    user = update.effective_user

    username = (
        f"@{user.username}"
        if user.username
        else "no_username"
    )

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    text = (
        f"{now} | "
        f"{username} ({user.id}) | "
        f"{category} | "
        f"{file_type}"
    )

    next_row = len(ws.col_values(10)) + 1

    ws.update_cell(next_row, 10, text)


def upload_to_drive(
    file_bytes,
    filename,
    mime_type,
    folder_id
):
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

    return (
        f"https://drive.google.com/"
        f"uc?export=download&id={file_id}"
    )

# ======================================================
# KEYBOARDS
# ======================================================

def kb_main(admin=False):
    kb = [
        ["Каталог", "Связаться", "Локация"]
    ]

    if admin:
        kb.append(["Админ панель"])

    return ReplyKeyboardMarkup(
        kb,
        resize_keyboard=True
    )


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

    await update.message.reply_text(
        "Меню",
        reply_markup=kb_main(is_admin(update))
    )

# ======================================================
# SEND PAGE
# ======================================================

async def send_page(update, context):
    u = context.user_data

    col = u.get("col")

    if not col:
        return

    values = ws.col_values(ord(col) - 64)

    if not values:
        await update.message.reply_text(
            "Пусто"
        )
        return

    for url in values:
        try:
            url = convert_drive_url(url)

            if col == "D":
                await context.bot.send_video(
                    update.effective_chat.id,
                    url
                )
            else:
                await context.bot.send_photo(
                    update.effective_chat.id,
                    url
                )

            await asyncio.sleep(0.3)

        except Exception as e:
            print("SEND ERROR:", e)

# ======================================================
# TEXT HANDLER
# ======================================================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    u = context.user_data

    # ===== ADMIN PANEL =====

    if text == "Админ панель" and is_admin(update):
        u["admin"] = True

        await update.message.reply_text(
            "Админ режим",
            reply_markup=kb_admin()
        )

        return

    # ===== BACK =====

    if text == "Назад":
        u["admin"] = False

        await update.message.reply_text(
            "Меню",
            reply_markup=kb_main(is_admin(update))
        )

        return

    # ===== MAIN =====

    if text == "Каталог":
        await update.message.reply_text(
            "Каталог",
            reply_markup=kb_catalog()
        )

        return

    if text == "Связаться":
        await update.message.reply_text(
            ws.acell("F1").value or "-"
        )

        return

    if text == "Локация":
        await update.message.reply_text(
            ws.acell("G1").value or "-"
        )

        return

    # ===== CATEGORY MAP =====

    mapping = {
        "Кухня": "A",
        "Спальня": "B",
        "Другое": "C",
        "Видео": "D",
        "Мягкая": "E"
    }

    # ===== ADMIN CATEGORY =====

    if u.get("admin") and text in mapping:
        u["upload_col"] = mapping[text]

        await update.message.reply_text(
            "Отправьте фото или видео",
            reply_markup=ReplyKeyboardRemove()
        )

        return

    # ===== USER CATEGORY =====

    if text in mapping:
        u["col"] = mapping[text]

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
        await update.message.reply_text(
            "❌ Категория не выбрана"
        )

        return

    file = None
    mime = "image/jpeg"
    file_type = "photo"

    try:

        # ===== PHOTO =====

        if update.message.photo:
            file = await update.message.photo[-1].get_file()

        # ===== VIDEO =====

        elif update.message.video:
            file = await update.message.video.get_file()

            mime = "video/mp4"
            file_type = "video"

        else:
            await update.message.reply_text(
                "❌ Unsupported file"
            )

            return

        data = await file.download_as_bytearray()

        folder_id = FOLDERS.get(col)

        if not folder_id:
            await update.message.reply_text(
                "❌ Folder ID not set"
            )

            return

        # ===== UPLOAD =====

        link = upload_to_drive(
            data,
            f"{datetime.now().timestamp()}",
            mime,
            folder_id
        )

        # ===== SAVE TO SHEET =====

        col_index = ord(col) - 64

        next_row = len(ws.col_values(col_index)) + 1

        ws.update_cell(
            next_row,
            col_index,
            link
        )

        # ===== LOG =====

        log(update, col, file_type)

        await update.message.reply_text(
            "✅ Загружено",
            reply_markup=kb_admin()
        )

    except Exception as e:
        print("UPLOAD ERROR:", e)

        await update.message.reply_text(
            f"❌ ERROR:\n{e}",
            reply_markup=kb_admin()
        )

# ======================================================
# WEBHOOK
# ======================================================

async def handle(request):
    data = await request.json()

    update = Update.de_json(
        data,
        request.app["bot"]
    )

    asyncio.create_task(
        request.app["app"].process_update(update)
    )

    return web.Response()


async def health(request):
    return web.Response(text="OK")

# ======================================================
# MAIN
# ======================================================

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

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

    webhook = (
        WEBHOOK_URL.rstrip("/")
        + "/"
        + BOT_TOKEN
    )

    print("WEBHOOK:", webhook)

    await app.bot.set_webhook(webhook)

    aio = web.Application()

    aio["bot"] = app.bot
    aio["app"] = app

    aio.router.add_post(
        f"/{BOT_TOKEN}",
        handle
    )

    aio.router.add_get("/", health)

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

# ======================================================
# RUN
# ======================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())

    except Exception as e:
        print("FATAL ERROR:")

        import traceback
        traceback.print_exc()
