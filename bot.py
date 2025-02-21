import os
import json
import requests
import asyncio
import platform
from flask import Flask
from threading import Thread
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes
from dotenv import load_dotenv

# Load environment variables if config file exists
CONFIG_FILE = "config_file.env"
if os.path.exists(CONFIG_FILE):
    load_dotenv(CONFIG_FILE)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
URL = os.getenv("URL")
CHAT_ID = os.getenv("CHAT_ID")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 5))  # Default: 5 seconds
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
PORT = int(os.getenv("PORT", 8080))

if not TELEGRAM_BOT_TOKEN or not URL or not GITHUB_REPO or not GITHUB_TOKEN:
    raise ValueError("Missing required environment variables!")

STORAGE_FILE = "latest_number.json"
app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

# Detect deployment platform
def detect_platform():
    platform_mapping = {
        "REPL_ID": "REPLIT",
        "FLY_ALLOC_ID": "FLY.IO",
        "RAILWAY_SERVICE_ID": "RAILWAY",
        "DYNO": "HEROKU",
        "GOOGLE_CLOUD_PROJECT": "GOOGLE_CLOUD",
        "AWS_EXECUTION_ENV": "AWS",
        "ORACLE_CLOUD": "ORACLE_CLOUD"
    }

    for env_var, platform in platform_mapping.items():
        if env_var in os.environ or os.getenv(env_var):
            return platform

    return "UNKNOWN"

DEPLOYMENT_PLATFORM = detect_platform()

def keep_alive():
    
    server = Flask(__name__)

    @server.route('/')
    def home():
        return f"Bot is running on {DEPLOYMENT_PLATFORM}"

    def run():
        server.run(host='0.0.0.0', port=PORT)

    Thread(target=run, daemon=True).start()


async def load_last_number():
    if os.path.exists(STORAGE_FILE):
        with open(STORAGE_FILE, "r") as f:
            data = json.load(f)
            return data.get("storedNum", None)
    return None


async def save_last_number(number):
    with open(STORAGE_FILE, "w") as f:
        json.dump({"storedNum": number}, f)


async def check_for_new_number():
    try:
        response = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None, None
    
    soup = BeautifulSoup(response.text, "html.parser")
    latest_title = soup.select_one('.latest-added__title a')
    new_number = int(latest_title.text.strip()) if latest_title else None
    flag_image = soup.select_one(".latest-added .container img")
    flag_url = flag_image.get("data-lazy-src").strip() if flag_image and flag_image.get("data-lazy-src") else None

    if flag_url and flag_url.startswith('//'):
        flag_url = f"https:{flag_url}"

    return new_number, flag_url


async def send_telegram_notification(number, flag_url):
    message = f"🎁 *New Number Added* 🎁\n\n`+{number}` check it out! 💖"
    keyboard = [[
        InlineKeyboardButton("📋 Copy Number", callback_data=f"copy_{number}"),
        InlineKeyboardButton("🔄 Update Number", callback_data=f"update_{number}")
    ], [
        InlineKeyboardButton(
            "🌐 Visit Webpage",
            url=f"{URL}/number/{number}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if CHAT_ID:
        try:
            if flag_url:
                await app.bot.send_photo(chat_id=CHAT_ID,
                                        photo=flag_url,
                                        caption=message,
                                        parse_mode="Markdown",
                                        reply_markup=reply_markup)
            else:
                await app.bot.send_message(chat_id=CHAT_ID,
                                        text=message,
                                        parse_mode="Markdown",
                                        reply_markup=reply_markup)
        except Exception as e:
            print(f"Failed to send notification: {e}")



async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action, number = query.data.split("_")
    if action == "copy":
        await query.answer("Number copied!", show_alert=False)
        await query.edit_message_reply_markup(
            InlineKeyboardMarkup([[InlineKeyboardButton("✅ Copied", callback_data=f"copy_{number}")]])
        )
    elif action == "update":
        await save_last_number(int(number))
        await query.edit_message_text(f"🔄 *Updated to:* `{number}`", parse_mode="Markdown")


async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    wait_time = int(args[0]) if args and args[0].isdigit() else None

    print("⛔ Stopping all tasks and will be restarted automatically...")
    print(f"⏳ Scheduling restart in {wait_time} seconds...")
        
    if args and args[0].isdigit():
        hours, remainder = divmod(wait_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        formatted_time = f"{hours:02}:{minutes:02}:{seconds:02}"

        message = await update.message.reply_text(f"⏳ Monitoring will stop for {formatted_time} for saving free hours 🎯. Countdown begins...")

        # Countdown loop
        for remaining in range(wait_time, 0, -1):
            hours, remainder = divmod(remaining, 3600)
            minutes, seconds = divmod(remainder, 60)
            countdown_text = f"Monitoring will stop for {hours} hours {minutes} minutes {seconds} seconds."
            
            try:
                await message.edit_text(countdown_text)
                await asyncio.sleep(1)
            except Exception:
                break
        
        if GITHUB_REPO and GITHUB_TOKEN:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/deploy.yml/dispatches"
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
            data = {"ref": "main"}

            response = requests.post(url, json=data, headers=headers)
            if response.status_code == 204:
                print("✅ GitHub Actions triggered successfully.")
            else:
                print(f"⚠️ Failed to trigger redeployment: {response.text}")

        sys.exit(0)
    else:
        await update.message.reply_text("⚠️ Please specify the number of seconds, e.g., `/stop 5000`")

async def monitor_website():
    last_number = await load_last_number()
    while True:
        new_number, flag_url = await check_for_new_number()
        if new_number and new_number != last_number:
            await send_telegram_notification(new_number, flag_url)
            await save_last_number(new_number)
            last_number = new_number
        await asyncio.sleep(CHECK_INTERVAL)


async def send_startup_message():
    if CHAT_ID:
        try:
            await app.bot.send_message(chat_id=CHAT_ID, text="At Your Service 🍒🍄")
            new_number, flag_url = await check_for_new_number()
            if new_number:
                await send_telegram_notification(new_number, flag_url)
                await save_last_number(new_number)
        except Exception as e:
            print(f"⚠️ Failed to send startup message: {e}")


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Received /ping command")
    await update.message.reply_text("I am now online 🌐")


async def main():
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("stop", stop_bot))
    
    keep_alive()
    
    print(f"✅ Bot is live on {DEPLOYMENT_PLATFORM}! I am now online 🌐")
    
    await app.initialize()
    await app.start()
    await asyncio.sleep(2)
    await send_startup_message()
    await monitor_website()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped gracefully")
