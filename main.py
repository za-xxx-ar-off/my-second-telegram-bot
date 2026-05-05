import os
import json
import asyncio
import logging
import gspread
from aiohttp import web

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)

print("BOT STARTING...")

# ===== ENV =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")
SERVICE_ACCOUNT_JSON = os.environ.get("SERVICE_ACCOUNT_JSON")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 10000))

if not all([BOT_TOKEN, SHEET_ID, SERVICE_ACCOUNT_JSON, WEBHOOK_URL]):
    raise ValueError("❌ Missing ENV variables")

# ===== GOOGLE SHEETS =====
creds = json.loads(SERVICE_ACCOUNT_JSON)
gc = gspread.service_account_from_dict(creds)
ws = gc.open_by_key(SHEET_ID).sheet1

# ===== SIMPLE HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is working 🚀")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"You said: {update.message.text}")

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

    await app.bot.set_webhook(f"{WEBHOOK_URL}/{BOT_TOKEN}")

    aio = web.Application()
    aio["bot"] = app.bot
    aio["app"] = app
    aio.router.add_post(f"/{BOT_TOKEN}", handle)

    runner = web.AppRunner(aio)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()

    print("SERVER STARTED")

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
