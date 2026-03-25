import os
import requests
import yfinance as yf
import pandas as pd

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYMBOLS = ["BTC-USD", "AAPL", "TSLA", "NVDA"]

def send_telegram(message: str) -> None:
    if not TOKEN or not CHAT_ID:
        print("Missing BOT_TOKEN or CHAT_ID")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        r = requests.post(url, data=payload, timeout=15)
        print("Telegram status:", r.status_code)
        print("Telegram response:", r.text)
    except Exception as e:
        print(f"Telegram error: {e}")

def analyze_symbol(symbol: str):
    try:
        print(f"Fetching {symbol}...")

        data = yf.download(
            symbol,
            period="5d",
            interval="5m",
            auto_adjust=True,
            progress=False
        )

        if data.empty or len(data) < 12:
            print(f"Not enough data for {symbol}")
            return None

        close_col = data["Close"]
        if isinstance(close_col, pd.DataFrame):
            close = close_col.iloc[:, 0]
        else:
            close = close_col

        sma10 = close.rolling(10).mean()

        prev_close = float(close.iloc[-2])
        last_close = float(close.iloc[-1])

        prev_sma = float(sma10.iloc[-2])
        last_sma = float(sma10.iloc[-1])

        if pd.isna(prev_sma) or pd.isna(last_sma):
            print(f"SMA not ready for {symbol}")
            return None

        buy_cross = prev_close <= prev_sma and last_close > last_sma
        sell_cross = prev_close >= prev_sma and last_close < last_sma

        if buy_cross:
            return {
                "symbol": symbol,
                "signal": "BUY",
                "price": round(last_close, 2),
                "tp": round(last_close * 1.02, 2),
                "sl": round(last_close * 0.98, 2)
            }

        if sell_cross:
            return {
                "symbol": symbol,
                "signal": "SELL",
                "price": round(last_close, 2)
            }

        print(f"No fresh signal for {symbol}")
        return None

    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")
        return None

def run_once() -> None:
    print("Bot started...")

    for symbol in SYMBOLS:
        result = analyze_symbol(symbol)
        if result is None:
            continue

        if result["signal"] == "BUY":
            msg = (
                f"🔥 BUY SIGNAL\n\n"
                f"Symbol: {result['symbol']}\n"
                f"Entry: {result['price']}\n"
                f"TP: {result['tp']}\n"
                f"SL: {result['sl']}"
            )
            send_telegram(msg)
            print(f"BUY sent for {symbol}")

        elif result["signal"] == "SELL":
            msg = (
                f"❌ SELL SIGNAL\n\n"
                f"Symbol: {result['symbol']}\n"
                f"Exit: {result['price']}"
            )
            send_telegram(msg)
            print(f"SELL sent for {symbol}")

    print("Finished")

if __name__ == "__main__":
    run_once()
