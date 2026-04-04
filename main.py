import os
import json
import logging
import gspread

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

print("BOT STARTING")

BOT_TOKEN = os.environ["BOT_TOKEN"]
SHEET_ID = os.environ["SHEET_ID"]
SERVICE_ACCOUNT_JSON = os.environ["SERVICE_ACCOUNT_JSON"]

print("ENV OK")

# Google Sheets
creds = json.loads(SERVICE_ACCOUNT_JSON)
gc = gspread.service_account_from_dict(creds)
sh = gc.open_by_key(SHEET_ID)
ws = sh.sheet1

print("GOOGLE SHEETS CONNECTED")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот работает ✅")


def main():

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    print("BOT STARTED")

    app.run_polling()


if __name__ == "__main__":
    main()
