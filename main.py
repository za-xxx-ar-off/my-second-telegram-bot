import os
import json
import asyncio
import logging
import gspread
from datetime import datetime
from aiohttp import web
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
print("BOT STARTING...")

logging.basicConfig(level=logging.INFO)

# ===== CONFIG =====
BOT_TOKEN = os.environ["BOT_TOKEN"]
SHEET_ID = os.environ["SHEET_ID"]
SERVICE_ACCOUNT_JSON = os.environ["SERVICE_ACCOUNT_JSON"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]
PORT = int(os.environ.get("PORT", 10000))

# ===== ADMIN IDS =====
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]

def is_admin(update):
    return update.effective_user.id in ADMIN_IDS

# ===== DRIVE FOLDERS =====
FOLDERS = {
    "A": os.environ.get("DRIVE_FOLDER_KITCHEN"),
    "B": os.environ.get("DRIVE_FOLDER_BEDROOM"),
    "C": os.environ.get("DRIVE_FOLDER_OTHER"),
    "D": os.environ.get("DRIVE_FOLDER_VIDEO"),
    "E": os.environ.get("DRIVE_FOLDER_SOFT"),
}

# ===== GOOGLE SHEETS =====
creds = json.loads(SERVICE_ACCOUNT_JSON)
gc = gspread.service_account_from_dict(creds)
sh = gc.open_by_key(SHEET_ID)
ws = sh.sheet1

# ===== DRIVE API =====
drive_service = build('drive', 'v3', credentials=gspread.service_account_from_dict(creds).auth)

# ===== TEXTS =====
TEXTS = {
    "ru": {
        "menu": "Меню",
        "catalog": "Каталог",
        "contact": "Связаться",
        "location": "Местоположение",
        "admin": "Админ панель",
        "back": "Назад",

        "kitchen": "Кухонные гарнитуры",
        "bedroom": "Спальни",
        "other": "Остальная мебель",
        "soft": "Мягкая мебель",
        "video": "Видео"
    }
}

# ===== KEYBOARDS =====
def kb_main(admin=False):
    kb = [["Каталог", "Связаться", "Местоположение"]]
    if admin:
        kb.append(["Админ панель"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def kb_admin():
    return ReplyKeyboardMarkup([
        ["Кухонные гарнитуры", "Спальни"],
        ["Остальная мебель", "Мягкая мебель"],
        ["Видео"],
        ["Назад"]
    ], resize_keyboard=True)

# ===== LOG TO SHEET J =====
def write_log(update, category, file_type):
    user = update.effective_user
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    username = f"@{user.username}" if user.username else "no_username"
    text = f"{now} | {username} ({user.id}) | {category} | {file_type}"

    col_index = 10  # J
    next_row = len(ws.col_values(col_index)) + 1
    ws.update_cell(next_row, col_index, text)

# ===== UPLOAD TO DRIVE =====
def upload_to_drive(file_bytes, filename, mime_type, folder_id):
    file_metadata = {'name': filename, 'parents': [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type)

    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()

    file_id = file.get('id')

    drive_service.permissions().create(
        fileId=file_id,
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()

    return f"https://drive.google.com/file/d/{file_id}/view"

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Меню", reply_markup=kb_main(is_admin(update)))

# ===== TEXT HANDLER =====
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    u = context.user_data

    if text == "Админ панель" and is_admin(update):
        u["admin"] = True
        await update.message.reply_text("Админ режим", reply_markup=kb_admin())
        return

    if text == "Назад":
        u["admin"] = False
        await update.message.reply_text("Меню", reply_markup=kb_main(is_admin(update)))
        return

    if u.get("admin"):
        mapping = {
            "Кухонные гарнитуры": "A",
            "Спальни": "B",
            "Остальная мебель": "C",
            "Видео": "D",
            "Мягкая мебель": "E",
        }

        if text in mapping:
            u["col"] = mapping[text]
            await update.message.reply_text("Отправьте файл")
            return

# ===== MEDIA HANDLER =====
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = context.user_data

    if not u.get("admin"):
        return

    col = u.get("col")
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

    link = upload_to_drive(data, "file", mime, folder_id)

    # ===== WRITE TO SHEET =====
    col_index = ord(col) - 64
    ws.update_cell(len(ws.col_values(col_index)) + 1, col_index, link)

    # ===== LOG =====
    write_log(update, col, file_type)

    await update.message.reply_text("Загружено")

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
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_media))

    await app.initialize()
    await app.start()

    await app.bot.set_webhook(WEBHOOK_URL + "/" + BOT_TOKEN)

    aio = web.Application()
    aio["bot"] = app.bot
    aio["app"] = app
    aio.router.add_post(f"/{BOT_TOKEN}", handle)

    runner = web.AppRunner(aio)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
