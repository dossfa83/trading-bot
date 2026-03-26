import os
import requests
import yfinance as yf
import pandas as pd

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

    df["EMA20"] = close.ewm(span=20, adjust=False).mean()
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

    typical_price = (high + low + close) / 3
    cumulative_tpv = (typical_price * volume).cumsum()
    cumulative_volume = volume.cumsum()
    df["VWAP"] = cumulative_tpv / cumulative_volume

    df["VOL_AVG20"] = volume.rolling(20).mean()

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()

    df["PREV_HIGH_20"] = high.shift(1).rolling(20).max()
    df["PREV_LOW_20"] = low.shift(1).rolling(20).min()

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

def score_to_strength(score: int) -> str:
    if score >= 7:
        return "ELITE"
    if score >= 6:
        return "HIGH"
    if score >= 4:
        return "MEDIUM"
    return "LOW"

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

        last5 = df5.iloc[-1]
        last15 = df15.iloc[-1]

        bullish_bias = (
            last15["Close"] > last15["EMA20"] > last15["EMA50"] and
            last15["RSI"] > 55 and
            last15["MACD"] > last15["MACD_SIGNAL"] and
            last15["Close"] > last15["VWAP"]
        )

        bearish_bias = (
            last15["Close"] < last15["EMA20"] < last15["EMA50"] and
            last15["RSI"] < 45 and
            last15["MACD"] < last15["MACD_SIGNAL"] and
            last15["Close"] < last15["VWAP"]
        )

        breakout_long = last5["Close"] > last5["PREV_HIGH_20"]
        breakdown_short = last5["Close"] < last5["PREV_LOW_20"]

        ema_confirm_long = last5["EMA20"] > last5["EMA50"]
        ema_confirm_short = last5["EMA20"] < last5["EMA50"]

        rsi_long = 55 <= last5["RSI"] <= 72
        rsi_short = 28 <= last5["RSI"] <= 45

        macd_long = last5["MACD"] > last5["MACD_SIGNAL"]
        macd_short = last5["MACD"] < last5["MACD_SIGNAL"]

        vwap_long = last5["Close"] > last5["VWAP"]
        vwap_short = last5["Close"] < last5["VWAP"]

        volume_spike = last5["Volume"] > 1.25 * last5["VOL_AVG20"]

        buy_signal = (
            bullish_bias and
            breakout_long and
            ema_confirm_long and
            rsi_long and
            macd_long and
            vwap_long and
            volume_spike
        )

        sell_signal = (
            bearish_bias and
            breakdown_short and
            ema_confirm_short and
            rsi_short and
            macd_short and
            vwap_short and
            volume_spike
        )

        price = round(float(last5["Close"]), 2)
        atr = float(last5["ATR"])

        entry_low = round(price - (0.15 * atr), 2)
        entry_high = round(price + (0.15 * atr), 2)
        ideal_entry = price

        stop_loss_long = round(price - (1.2 * atr), 2)
        tp1_long = round(price + (1.2 * atr), 2)
        tp2_long = round(price + (2.0 * atr), 2)
        tp3_long = round(price + (3.0 * atr), 2)

        stop_loss_short = round(price + (1.2 * atr), 2)
        tp1_short = round(price - (1.2 * atr), 2)
        tp2_short = round(price - (2.0 * atr), 2)
        tp3_short = round(price - (3.0 * atr), 2)

        long_score = 0
        long_score += int(bullish_bias)
        long_score += int(breakout_long)
        long_score += int(ema_confirm_long)
        long_score += int(rsi_long)
        long_score += int(macd_long)
        long_score += int(vwap_long)
        long_score += int(volume_spike)

        short_score = 0
        short_score += int(bearish_bias)
        short_score += int(breakdown_short)
        short_score += int(ema_confirm_short)
        short_score += int(rsi_short)
        short_score += int(macd_short)
        short_score += int(vwap_short)
        short_score += int(volume_spike)

        if buy_signal:
            return {
                "signal": "BUY",
                "setup_type": "Momentum Breakout Long",
                "price": price,
                "entry_low": entry_low,
                "entry_high": entry_high,
                "ideal_entry": ideal_entry,
                "sl": stop_loss_long,
                "tp1": tp1_long,
                "tp2": tp2_long,
                "tp3": tp3_long,
                "atr": round(atr, 2),
                "rsi_5m": round(float(last5["RSI"]), 2),
                "rsi_15m": round(float(last15["RSI"]), 2),
                "strength": score_to_strength(long_score),
                "score": long_score,
                "reasons": [
                    "15m bullish trend confirmed",
                    "5m breakout above recent high",
                    "Price above VWAP",
                    "MACD bullish confirmation",
                    "Volume expansion detected"
                ]
            }

        if sell_signal:
            return {
                "signal": "SELL",
                "setup_type": "Momentum Breakdown Short",
                "price": price,
                "entry_low": entry_low,
                "entry_high": entry_high,
                "ideal_entry": ideal_entry,
                "sl": stop_loss_short,
                "tp1": tp1_short,
                "tp2": tp2_short,
                "tp3": tp3_short,
                "atr": round(atr, 2),
                "rsi_5m": round(float(last5["RSI"]), 2),
                "rsi_15m": round(float(last15["RSI"]), 2),
                "strength": score_to_strength(short_score),
                "score": short_score,
                "reasons": [
                    "15m bearish trend confirmed",
                    "5m breakdown below recent low",
                    "Price below VWAP",
                    "MACD bearish confirmation",
                    "Volume expansion detected"
                ]
            }

        print("No elite setup.")
        return None

    except Exception as e:
        print(f"Analyze error: {e}")
        return None

def format_trade_message(result: dict) -> str:
    reasons_text = "\n".join([f"- {r}" for r in result["reasons"]])

    if result["signal"] == "BUY":
        direction = "LONG"
        plan = (
            "Trade Plan:\n"
            "- Enter only if price holds above entry zone.\n"
            "- Secure part of profits at TP1.\n"
            "- Move stop toward breakeven after TP1.\n"
            "- Let runner target TP2 / TP3 if momentum stays strong."
        )
        emoji = "🔥"
        title = "BTC ELITE SCALP SETUP"

    else:
        direction = "SHORT"
        plan = (
            "Trade Plan:\n"
            "- Enter only if price stays below entry zone.\n"
            "- Secure part of profits at TP1.\n"
            "- Tighten risk after TP1.\n"
            "- Let runner target TP2 / TP3 if downside momentum continues."
        )
        emoji = "❌"
        title = "BTC ELITE SHORT SETUP"

    return (
        f"{emoji} {title}\n\n"
        f"Direction: {direction}\n"
        f"Setup Type: {result['setup_type']}\n"
        f"Entry Zone: {result['entry_low']} - {result['entry_high']}\n"
        f"Ideal Entry: {result['ideal_entry']}\n"
        f"Stop Loss: {result['sl']}\n"
        f"Target 1: {result['tp1']}\n"
        f"Target 2: {result['tp2']}\n"
        f"Target 3: {result['tp3']}\n\n"
        f"Signal Strength: {result['strength']} ({result['score']}/7)\n"
        f"ATR: {result['atr']}\n"
        f"RSI 5m: {result['rsi_5m']}\n"
        f"RSI 15m: {result['rsi_15m']}\n\n"
        f"Confirmation:\n{reasons_text}\n\n"
        f"{plan}"
    )

def run_once() -> None:
    print("Bot started...")
    result = analyze_btc()

    if result is None:
        msg = "📊 BTC CHECK\n\nNo elite setup right now."
        send_telegram(msg)
        print("No signal sent to Telegram")
        return

    msg = format_trade_message(result)
    send_telegram(msg)
    print(f"{result['signal']} sent")
    print("Finished")

if __name__ == "__main__":
    run_once()
