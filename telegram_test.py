import os
import json
import requests
import yfinance as yf
import pandas as pd

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        print("Missing BOT_TOKEN or CHAT_ID")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}

    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

symbols = ["AAPL", "TSLA"]

def analyze_symbol(symbol):
    try:
        print(f"Fetching {symbol}...")

        data = yf.download(
            symbol,
            period="5d",
            interval="5m",
            progress=False,
            timeout=10
        )

        if data.empty:
            print(f"No data for {symbol}")
            return None

        close = data["Close"]

        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]

        last = float(close.iloc[-1])
        sma = float(close.rolling(10).mean().iloc[-1])

        if last > sma:
            return f"BUY {symbol} @ {round(last,2)}"
        else:
            return f"SELL {symbol} @ {round(last,2)}"

    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

def run_once():
    print("Bot started...")

    for symbol in symbols:
        result = analyze_symbol(symbol)

        if result:
            print(result)
            send_telegram(result)

    print("Finished")

if __name__ == "__main__":
    run_once()
