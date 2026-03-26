import os
import requests
import yfinance as yf
import pandas as pd
import numpy as np

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYMBOL = "BTC-USD"

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

def normalize_ohlcv(data: pd.DataFrame) -> pd.DataFrame:
    if isinstance(data.columns, pd.MultiIndex):
        df = pd.DataFrame({
            "Open": data["Open"].iloc[:, 0],
            "High": data["High"].iloc[:, 0],
            "Low": data["Low"].iloc[:, 0],
            "Close": data["Close"].iloc[:, 0],
            "Volume": data["Volume"].iloc[:, 0],
        })
    else:
        df = data[["Open", "High", "Low", "Close", "Volume"]].copy()

    return df.dropna().copy()

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # Trend EMAs
    df["EMA20"] = close.ewm(span=20, adjust=False).mean()
    df["EMA50"] = close.ewm(span=50, adjust=False).mean()

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()

    # VWAP
    typical_price = (high + low + close) / 3
    cumulative_tpv = (typical_price * volume).cumsum()
    cumulative_volume = volume.cumsum()
    df["VWAP"] = cumulative_tpv / cumulative_volume

    # Volume
    df["VOL_AVG20"] = volume.rolling(20).mean()

    # ATR (Average True Range)
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()

    # آخر 20 قمة لتأكيد الاختراق
    df["ROLLING_HIGH20"] = high.rolling(20).max()

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
        return normalize_ohlcv(raw)
    except Exception as e:
        print(f"Fetch error {symbol} {interval}: {e}")
        return None

def confidence_label(score: int) -> str:
    if score >= 6:
        return "High"
    if score >= 4:
        return "Medium"
    return "Low"

def analyze_btc():
    try:
        print("Analyzing BTC-USD...")

        df5 = fetch_data(SYMBOL, interval="5m", period="5d")
        df15 = fetch_data(SYMBOL, interval="15m", period="5d")

        if df5 is None or df15 is None:
            print("No data")
            return None

        df5 = add_indicators(df5).dropna().copy()
        df15 = add_indicators(df15).dropna().copy()

        if len(df5) < 30 or len(df15) < 30:
            print("Not enough indicator data")
            return None

        prev5 = df5.iloc[-2]
        last5 = df5.iloc[-1]
        last15 = df15.iloc[-1]

        # اتجاه عام محترف على 15m
        trend_up_15m = (
            last15["Close"] > last15["EMA20"] > last15["EMA50"] and
            last15["RSI"] > 55 and
            last15["MACD"] > last15["MACD_SIGNAL"]
        )

        trend_down_15m = (
            last15["Close"] < last15["EMA20"] and
            last15["EMA20"] < last15["EMA50"] and
            last15["MACD"] < last15["MACD_SIGNAL"]
        )

        # دخول احترافي على 5m:
        # اختراق + فوق VWAP + زخم + فوليوم
        breakout = last5["Close"] > prev5["ROLLING_HIGH20"]
        ema_confirm = last5["EMA20"] > last5["EMA50"]
        rsi_confirm = 55 <= last5["RSI"] <= 72
        macd_confirm = last5["MACD"] > last5["MACD_SIGNAL"]
        vwap_confirm = last5["Close"] > last5["VWAP"]
        volume_confirm = last5["Volume"] > 1.2 * last5["VOL_AVG20"]

        buy_signal = (
            trend_up_15m and
            breakout and
            ema_confirm and
            rsi_confirm and
            macd_confirm and
            vwap_confirm and
            volume_confirm
        )

        # خروج احترافي إذا ضعف الاتجاه
        sell_signal = (
            trend_down_15m and
            last5["MACD"] < last5["MACD_SIGNAL"] and
            last5["Close"] < last5["EMA20"]
        )

        price = round(float(last5["Close"]), 2)
        atr = float(last5["ATR"])

        # وقف وهدف مبنيين على ATR
        stop_loss = round(price - (1.2 * atr), 2)
        take_profit_1 = round(price + (1.5 * atr), 2)
        take_profit_2 = round(price + (2.5 * atr), 2)

        # درجة الثقة
        score = 0
        score += int(trend_up_15m)
        score += int(breakout)
        score += int(ema_confirm)
        score += int(rsi_confirm)
        score += int(macd_confirm)
        score += int(vwap_confirm)
        score += int(volume_confirm)
        confidence = confidence_label(score)

        if buy_signal:
            return {
                "signal": "BUY",
                "price": price,
                "tp1": take_profit_1,
                "tp2": take_profit_2,
                "sl": stop_loss,
                "atr": round(atr, 2),
                "rsi_5m": round(float(last5["RSI"]), 2),
                "rsi_15m": round(float(last15["RSI"]), 2),
                "confidence": confidence,
                "score": score
            }

        if sell_signal:
            return {
                "signal": "SELL",
                "price": price,
                "rsi_5m": round(float(last5["RSI"]), 2),
                "rsi_15m": round(float(last15["RSI"]), 2),
                "confidence": confidence,
                "score": score
            }

        print("No fresh signal.")
        return None

    except Exception as e:
        print(f"Analyze error: {e}")
        return None

def run_once() -> None:
    print("Bot started...")

    result = analyze_btc()

    if result is None:
        print("Finished - no signal")
        return

    if result["signal"] == "BUY":
        msg = (
            f"🔥 BTC BUY SIGNAL PRO\n\n"
            f"Symbol: {SYMBOL}\n"
            f"Buy Price: {result['price']}\n"
            f"Take Profit 1: {result['tp1']}\n"
            f"Take Profit 2: {result['tp2']}\n"
            f"Stop Loss: {result['sl']}\n"
            f"ATR: {result['atr']}\n"
            f"RSI 5m: {result['rsi_5m']}\n"
            f"RSI 15m: {result['rsi_15m']}\n"
            f"Confidence: {result['confidence']} ({result['score']}/7)"
        )
        send_telegram(msg)
        print("BUY sent")

    elif result["signal"] == "SELL":
        msg = (
            f"❌ BTC SELL / EXIT SIGNAL PRO\n\n"
            f"Symbol: {SYMBOL}\n"
            f"Exit Price: {result['price']}\n"
            f"RSI 5m: {result['rsi_5m']}\n"
            f"RSI 15m: {result['rsi_15m']}\n"
            f"Confidence: {result['confidence']} ({result['score']}/7)"
        )
        send_telegram(msg)
        print("SELL sent")

    print("Finished")

if __name__ == "__main__":
    run_once()
