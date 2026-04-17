import os
import json
import logging
import gspread
from aiohttp import web

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
SHEET_ID = os.environ["SHEET_ID"]
SERVICE_ACCOUNT_JSON = os.environ["SERVICE_ACCOUNT_JSON"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]
PORT = int(os.environ.get("PORT", 10000))

# Google Sheets
creds = json.loads(SERVICE_ACCOUNT_JSON)
gc = gspread.service_account_from_dict(creds)
sh = gc.open_by_key(SHEET_ID)
ws = sh.sheet1


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот работает ✅")


async def handle(request):
    data = await request.json()
    update = Update.de_json(data, request.app["bot"])
    await request.app["app"].process_update(update)
    return web.Response()


async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

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

    # держим процесс живым
    import asyncio
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
