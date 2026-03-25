import os
import json
import requests
import yfinance as yf
import pandas as pd

# =========================
# Telegram Settings
# =========================
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        print("Missing BOT_TOKEN or CHAT_ID")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

# =========================
# Settings
# =========================
symbols = ["AAPL", "TSLA", "NVDA"]

# =========================
# Load / Save State
# =========================
STATE_FILE = "trade_state.json"

def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# =========================
# Strategy (بسيطة)
# =========================
def analyze_symbol(symbol):
    try:
        data = yf.download(symbol, period="1d", interval="1m")

        if data.empty:
            return None

        last_close = float(data["Close"].iloc[-1])
        sma = float(data["Close"].rolling(10).mean().iloc[-1])

        position = 1 if last_close > sma else 0

        return {
            "symbol": symbol,
            "position": position,
            "last_close": last_close,
            "stop_loss": round(last_close * 0.98, 2),
            "take_profit": round(last_close * 1.02, 2),
            "trailing_exit": round(last_close * 0.99, 2)
        }

    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

# =========================
# Run Once (بدون لوب)
# =========================
def run_once():
    print("Bot started...")

    state = load_state()

    for symbol in symbols:
        result = analyze_symbol(symbol)

        if result is None:
            continue

        old = state.get(symbol, {"position": 0})

        old_pos = int(old.get("position", 0))
        new_pos = int(result["position"])

        # BUY
        if old_pos == 0 and new_pos == 1:
            msg = (
                f"🔥 BUY SIGNAL\n\n"
                f"{symbol}\n"
                f"Entry: {result['last_close']}\n"
                f"TP: {result['take_profit']}\n"
                f"SL: {result['stop_loss']}"
            )
            send_telegram(msg)
            print(f"BUY {symbol}")

        # SELL
        elif old_pos == 1 and new_pos == 0:
            msg = (
                f"❌ SELL SIGNAL\n\n"
                f"{symbol}\n"
                f"Exit: {result['last_close']}"
            )
            send_telegram(msg)
            print(f"SELL {symbol}")

        state[symbol] = result

    save_state(state)
    print("Finished")

# =========================
# Main
# =========================
if __name__ == "__main__":
    run_once()
