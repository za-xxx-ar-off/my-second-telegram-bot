import os
import json
import asyncio
import logging
import gspread
from datetime import datetime
from aiohttp import web
import io

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from telegram import Update, ReplyKeyboardMarkup
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
creds_dict = json.loads(SERVICE_ACCOUNT_JSON)

gc = gspread.service_account_from_dict(creds_dict)
sh = gc.open_by_key(SHEET_ID)
ws = sh.sheet1

# ===== GOOGLE DRIVE AUTH FIX =====
SCOPES = ["https://www.googleapis.com/auth/drive"]
credentials = service_account.Credentials.from_service_account_info(
    creds_dict,
    scopes=SCOPES
)

drive_service = build("drive", "v3", credentials=credentials)

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

# ===== LOG =====
def write_log(update, category, file_type):
    user = update.effective_user
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    username = f"@{user.username}" if user.username else "no_username"
    text = f"{now} | {username} ({user.id}) | {category} | {file_type}"

    ws.update_cell(len(ws.col_values(10)) + 1, 10, text)  # column J

# ===== DRIVE UPLOAD =====
def upload_to_drive(file_bytes, filename, mime_type, folder_id):
    file_metadata = {
        "name": filename,
        "parents": [folder_id]
    }

    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type)

    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    file_id = file.get("id")

    drive_service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"}
    ).execute()

    return f"https://drive.google.com/file/d/{file_id}/view"

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Меню", reply_markup=kb_main(is_admin(update)))

# ===== TEXT =====
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
            await update.message.reply_text("Отправьте фото или видео")
            return

# ===== MEDIA =====
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = context.user_data

    if not u.get("admin"):
        return

    col = u.get("col")
    if not col:
        return

    folder_id = FOLDERS.get(col)

    file_obj = None
    mime = "image/jpeg"
    file_type = "photo"

    if update.message.photo:
        file_obj = await update.message.photo[-1].get_file()
    elif update.message.video:
        file_obj = await update.message.video.get_file()
        mime = "video/mp4"
        file_type = "video"
    else:
        return

    data = await file_obj.download_as_bytearray()

    link = upload_to_drive(data, "file", mime, folder_id)

    # write to sheet
    col_index = ord(col) - 64
    ws.update_cell(len(ws.col_values(col_index)) + 1, col_index, link)

    # log
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

    print("SERVER RUNNING")

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
