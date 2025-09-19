# auto_bot.py
# Telegram Auto Response Bot for Trading Groups + Live Prices (BTC, ETH, BNB, SOL, XAU/USD) via CoinGecko API
# Timezone set to Asia/Bangkok (UTC+7)
# Ready for Render / Railway deployment

import os
import json
import datetime
import asyncio
import requests
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# =========================
# Load bot credentials
# =========================
TOKEN = os.getenv("TOKEN")
GROUP_ID = os.getenv("GROUP_ID")

if not TOKEN or not GROUP_ID:
    raise ValueError("ERROR: TOKEN or GROUP_ID not set in environment variables!")

GROUP_ID = int(GROUP_ID)

# =========================
# File paths
# =========================
PRICES_FILE = "prices.json"
RESPONSES_FILE = "responses.json"

# =========================
# Ensure JSON files exist
# =========================
if not os.path.exists(RESPONSES_FILE):
    default_responses = {
        "hello": "👋 Welcome to our Trading Group! Type 'help' for commands.",
        "help": "📌 Commands:\n- /price: Check live prices\n- deposit: How to deposit funds\n- withdraw: Withdrawal guide",
        "_welcome": "👋 Welcome {name} to our Trading Group!",
        "_reload_success": "🔄 Responses reloaded successfully!",
    }
    with open(RESPONSES_FILE, "w", encoding="utf-8") as f:
        json.dump(default_responses, f, indent=4, ensure_ascii=False)

if not os.path.exists(PRICES_FILE):
    with open(PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

# =========================
# Market tickers for CoinGecko
# =========================
TICKERS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XAU": "tether-gold",  # Gold token on CoinGecko
}

last_prices = {}


# =========================
# Load / Save prices
# =========================
def load_last_prices():
    try:
        with open(PRICES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_last_prices(prices):
    try:
        with open(PRICES_FILE, "w", encoding="utf-8") as f:
            json.dump(prices, f, indent=4)
    except Exception as e:
        print(f"Error saving prices.json: {e}")


last_prices = load_last_prices()


# =========================
# Load responses
# =========================
def load_responses():
    try:
        with open(RESPONSES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


responses = load_responses()


# =========================
# Fetch live market prices
# =========================
def get_market_prices():
    global last_prices
    prices = {}
    try:
        coin_ids = ",".join(TICKERS.values())
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_ids}&vs_currencies=usd"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        for name, coin_id in TICKERS.items():
            try:
                current_price = round(float(data[coin_id]["usd"]), 2)
                arrow = " ➡️"
                if name in last_prices:
                    if current_price > last_prices[name]:
                        arrow = " 🔼"
                    elif current_price < last_prices[name]:
                        arrow = " 🔽"
                last_prices[name] = current_price
                prices[name] = (current_price, arrow)
            except:
                prices[name] = (None, " ❓")
    except Exception as e:
        print(f"Error fetching CoinGecko data: {e}")
        for name in TICKERS.keys():
            prices[name] = (None, " ❓")

    save_last_prices(last_prices)
    return prices


# =========================
# Format message with Bangkok time
# =========================
def format_market_message(prices, title="💹 Live Market Prices"):
    now = datetime.datetime.now(ZoneInfo("Asia/Bangkok"))
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    message = f"{title} ({timestamp}):\n\n"
    for coin, (price, arrow) in prices.items():
        if price is not None:
            symbol = (
                "💰" if coin == "BTC" else
                "💎" if coin == "ETH" else
                "🟡" if coin == "BNB" else
                "🟣" if coin == "SOL" else
                "🏅"
            )
            message += f"{symbol} {coin}/USD: ${price:,.2f}{arrow}\n"
        else:
            message += f"⚠️ {coin}/USD: N/A{arrow}\n"
    message += "\n💰 One trade is enough to change your life 💸"
    return message


# =========================
# Scheduled updates (Bangkok time)
# =========================
async def send_market_update(app: Application):
    prices = get_market_prices()
    message = format_market_message(prices, "📊 Market Update")
    await app.bot.send_message(chat_id=GROUP_ID, text=message)


async def schedule_updates(app: Application):
    target_times = [(9, 0), (12, 0), (19, 0)]
    sent_today = set()
    while True:
        now = datetime.datetime.now(ZoneInfo("Asia/Bangkok"))
        for hour, minute in target_times:
            if now.hour == hour and now.minute == minute:
                key = (now.date(), hour, minute)
                if key not in sent_today:
                    await send_market_update(app)
                    sent_today.add(key)
        if now.hour == 0 and now.minute == 0:
            sent_today.clear()
        await asyncio.sleep(30)


# =========================
# Handlers
# =========================
async def handle_price_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = get_market_prices()
    message = format_market_message(prices)
    await update.message.reply_text(message)


async def auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    msg = update.message.text.lower()
    if "price" in msg or msg.startswith("/price"):
        await handle_price_request(update, context)
        return
    for keyword, reply in responses.items():
        if keyword.startswith("_"):
            continue
        if keyword in msg:
            await update.message.reply_text(reply)
            return


async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status
    if old_status in ("left", "kicked") and new_status == "member":
        new_user = result.new_chat_member.user
        welcome_message = responses.get("_welcome", "👋 Welcome {name}!")
        welcome_message = welcome_message.replace("{name}", new_user.mention_html())
        await context.bot.send_message(
            chat_id=update.chat_member.chat.id,
            text=welcome_message,
            parse_mode="HTML",
        )


async def reload_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global responses
    responses = load_responses()
    await update.message.reply_text(responses.get("_reload_success", "Reloaded!"))


# =========================
# Main
# =========================
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_reply))
    app.add_handler(ChatMemberHandler(welcome, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CommandHandler("price", handle_price_request))
    app.add_handler(CommandHandler("reload", reload_responses))

    async def on_startup(_):
        asyncio.create_task(schedule_updates(app))

    app.post_init = on_startup

    print("🤖 Bot is running... Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
