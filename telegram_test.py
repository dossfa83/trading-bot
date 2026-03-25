import os
import json
import requests
import yfinance as yf
import pandas as pd

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYMBOLS = ["BTC-USD", "AAPL", "TSLA", "NVDA"]
STATE_FILE = "signal_state.json"

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

def load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def normalize_ohlcv(data: pd.DataFrame) -> pd.DataFrame:
    if isinstance(data.columns, pd.MultiIndex):
        return pd.DataFrame({
            "Open": data["Open"].iloc[:, 0],
            "High": data["High"].iloc[:, 0],
            "Low": data["Low"].iloc[:, 0],
            "Close": data["Close"].iloc[:, 0],
            "Volume": data["Volume"].iloc[:, 0],
        }).dropna()
    return data[["Open", "High", "Low", "Close", "Volume"]].dropna().copy()

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    close = df["Close"]
    volume = df["Volume"]

    df["EMA9"] = close.ewm(span=9, adjust=False).mean()
    df["EMA21"] = close.ewm(span=21, adjust=False).mean()
    df["EMA50"] = close.ewm(span=50, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()

    df["VOL_AVG20"] = volume.rolling(20).mean()
    return df

def fetch_data(symbol: str, interval: str, period: str) -> pd.DataFrame | None:
    try:
        raw = yf.download(
            symbol,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False
        )
        if raw.empty:
            return None
        df = normalize_ohlcv(raw)
        return df if not df.empty else None
    except Exception as e:
        print(f"Fetch error {symbol} {interval}: {e}")
        return None

def get_market_filter() -> bool:
    """
    يرجع True إذا السوق العام مناسب للشراء.
    نستخدم SPY للأسهم فقط. البيتكوين ما يحتاج هذا الفلتر.
    """
    try:
        spy = fetch_data("SPY", interval="15m", period="5d")
        if spy is None or len(spy) < 60:
            print("SPY filter unavailable, defaulting to True")
            return True

        spy = add_indicators(spy).dropna()
        if len(spy) < 2:
            return True

        last = spy.iloc[-1]
        market_ok = (
            last["EMA9"] > last["EMA21"] > last["EMA50"] and
            last["MACD"] > last["MACD_SIGNAL"] and
            last["RSI"] > 50
        )

        print("Market filter SPY:", market_ok)
        return bool(market_ok)
    except Exception as e:
        print("Market filter error:", e)
        return True

def confidence_score(last5, last15):
    score = 0

    if last5["EMA9"] > last5["EMA21"]:
        score += 1
    if last15["EMA9"] > last15["EMA21"]:
        score += 1
    if last15["EMA21"] > last15["EMA50"]:
        score += 1
    if last5["MACD"] > last5["MACD_SIGNAL"]:
        score += 1
    if last15["MACD"] > last15["MACD_SIGNAL"]:
        score += 1
    if last5["Volume"] > last5["VOL_AVG20"]:
        score += 1
    if 52 <= last5["RSI"] <= 68:
        score += 1

    if score >= 6:
        return "High", score
    elif score >= 4:
        return "Medium", score
    else:
        return "Low", score

def analyze_symbol(symbol: str, market_ok: bool):
    try:
        print(f"Analyzing {symbol}...")

        df5 = fetch_data(symbol, interval="5m", period="5d")
        df15 = fetch_data(symbol, interval="15m", period="5d")

        if df5 is None or df15 is None:
            print(f"No data for {symbol}")
            return None

        df5 = add_indicators(df5).dropna().copy()
        df15 = add_indicators(df15).dropna().copy()

        if len(df5) < 5 or len(df15) < 5:
            print(f"Not enough indicator data for {symbol}")
            return None

        prev5 = df5.iloc[-2]
        last5 = df5.iloc[-1]
        last15 = df15.iloc[-1]

        # فلتر السوق يطبق على الأسهم فقط، مو البيتكوين
        use_market_filter = symbol != "BTC-USD"

        trend_up_15m = (
            last15["EMA9"] > last15["EMA21"] > last15["EMA50"] and
            last15["RSI"] > 52 and
            last15["MACD"] > last15["MACD_SIGNAL"]
        )

        trend_down_15m = (
            last15["EMA9"] < last15["EMA21"] and
            last15["MACD"] < last15["MACD_SIGNAL"]
        )

        buy_cross_5m = prev5["EMA9"] <= prev5["EMA21"] and last5["EMA9"] > last5["EMA21"]
        sell_cross_5m = prev5["EMA9"] >= prev5["EMA21"] and last5["EMA9"] < last5["EMA21"]

        buy_signal = (
            trend_up_15m and
            buy_cross_5m and
            52 <= last5["RSI"] <= 68 and
            last5["MACD"] > last5["MACD_SIGNAL"] and
            last5["Volume"] > last5["VOL_AVG20"] and
            (market_ok if use_market_filter else True)
        )

        sell_signal = (
            trend_down_15m and
            sell_cross_5m
        )

        last_close = round(float(last5["Close"]), 2)
        confidence, score = confidence_score(last5, last15)

        if buy_signal:
            return {
                "symbol": symbol,
                "signal": "BUY",
                "price": last_close,
                "tp": round(last_close * 1.03, 2),
                "sl": round(last_close * 0.985, 2),
                "rsi_5m": round(float(last5["RSI"]), 2),
                "rsi_15m": round(float(last15["RSI"]), 2),
                "confidence": confidence,
                "score": score
            }

        if sell_signal:
            return {
                "symbol": symbol,
                "signal": "SELL",
                "price": last_close,
                "rsi_5m": round(float(last5["RSI"]), 2),
                "rsi_15m": round(float(last15["RSI"]), 2),
                "confidence": confidence,
                "score": score
            }

        print(f"No fresh signal for {symbol}")
        return None

    except Exception as e:
        print(f"Analyze error {symbol}: {e}")
        return None

def run_once() -> None:
    print("Bot started...")
    market_ok = get_market_filter()
    state = load_state()

    for symbol in SYMBOLS:
        result = analyze_symbol(symbol, market_ok)
        current_signal = result["signal"] if result else "NONE"
        previous_signal = state.get(symbol, "NONE")

        # لا ترسل إذا نفس الإشارة السابقة
        if current_signal == previous_signal:
            print(f"Skipping duplicate signal for {symbol}: {current_signal}")
            continue

        # حدث الحالة دائمًا
        state[symbol] = current_signal

        if result is None:
            continue

        if result["signal"] == "BUY":
            msg = (
                f"🔥 BUY SIGNAL PRO+ 2\n\n"
                f"Symbol: {result['symbol']}\n"
                f"Entry: {result['price']}\n"
                f"TP: {result['tp']}\n"
                f"SL: {result['sl']}\n"
                f"RSI 5m: {result['rsi_5m']}\n"
                f"RSI 15m: {result['rsi_15m']}\n"
                f"Confidence: {result['confidence']} ({result['score']}/7)"
            )
            send_telegram(msg)
            print(f"BUY sent for {symbol}")

        elif result["signal"] == "SELL":
            msg = (
                f"❌ SELL SIGNAL PRO+ 2\n\n"
                f"Symbol: {result['symbol']}\n"
                f"Exit: {result['price']}\n"
                f"RSI 5m: {result['rsi_5m']}\n"
                f"RSI 15m: {result['rsi_15m']}\n"
                f"Confidence: {result['confidence']} ({result['score']}/7)"
            )
            send_telegram(msg)
            print(f"SELL sent for {symbol}")

    save_state(state)
    print("Finished")

if __name__ == "__main__":
    run_once()
