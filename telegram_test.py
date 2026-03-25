import os

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
import requests
import yfinance as yf
import pandas as pd
import json
import os
import time

# =========================
# Telegram Settings
# =========================
TOKEN = "7993018592:AAHKBtm2t-E5hZ2viHYY5a9L09MIkpNYqhk"
CHAT_ID = "385184537"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, data=payload, timeout=15)

# =========================
# Trading Settings
# =========================
symbols = [
    "AAPL",
    "MSFT",
    "NVDA",
    "META",
    "TSLA",
    "AMD",
    "AMZN",
    "NFLX",
    "COIN",
    "MARA"
]

interval = "5m"
period = "5d"

stop_loss_pct = 0.02
take_profit_pct = 0.03
trailing_stop_pct = 0.03

STATE_FILE = "trade_state.json"

# =========================
# State Helpers
# =========================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# =========================
# Analyze One Symbol
# =========================
def analyze_symbol(symbol):
    raw = yf.download(
        symbol,
        period=period,
        interval=interval,
        auto_adjust=True,
        progress=False,
        prepost=False
    )

    if raw.empty or len(raw) < 50:
        return None

    if isinstance(raw.columns, pd.MultiIndex):
        data = pd.DataFrame({
            "Open": raw["Open"][symbol],
            "High": raw["High"][symbol],
            "Low": raw["Low"][symbol],
            "Close": raw["Close"][symbol],
            "Volume": raw["Volume"][symbol]
        })
    else:
        data = raw[["Open", "High", "Low", "Close", "Volume"]].copy()

    data = data.dropna().copy()

    if len(data) < 30:
        return None

    # =========================
    # Indicators
    # =========================
    data["EMA9"] = data["Close"].ewm(span=9, adjust=False).mean()
    data["EMA21"] = data["Close"].ewm(span=21, adjust=False).mean()

    typical_price = (data["High"] + data["Low"] + data["Close"]) / 3
    cumulative_tpv = (typical_price * data["Volume"]).cumsum()
    cumulative_volume = data["Volume"].cumsum()
    data["VWAP"] = cumulative_tpv / cumulative_volume

    data["AvgVol20"] = data["Volume"].rolling(20).mean()
    data["High20"] = data["High"].rolling(20).max()

    # =========================
    # Entry Signal
    # =========================
    data["EntrySignal"] = 0
    data.loc[
        (data["Close"] > data["EMA9"]) &
        (data["EMA9"] > data["EMA21"]) &
        (data["Close"] > data["VWAP"]) &
        (data["Close"] >= data["High20"].shift(1)) &
        (data["Volume"] > 1.5 * data["AvgVol20"]) &
        (data["Close"] > data["Open"]),
        "EntrySignal"
    ] = 1

    # =========================
    # Trade Management
    # =========================
    position = 0
    entry_price = 0.0
    highest_price = 0.0

    positions = []
    entry_prices = []
    highest_prices = []

    for i in range(len(data)):
        close_price = data["Close"].iloc[i]
        ema9 = data["EMA9"].iloc[i]
        ema21 = data["EMA21"].iloc[i]
        vwap = data["VWAP"].iloc[i]
        entry_signal = data["EntrySignal"].iloc[i]

        if position == 0:
            if entry_signal == 1:
                position = 1
                entry_price = close_price
                highest_price = close_price
        else:
            if close_price > highest_price:
                highest_price = close_price

            pnl = (close_price - entry_price) / entry_price
            drawdown_from_high = (close_price - highest_price) / highest_price

            if pnl <= -stop_loss_pct:
                position = 0
                entry_price = 0.0
                highest_price = 0.0
            elif pnl >= take_profit_pct:
                position = 0
                entry_price = 0.0
                highest_price = 0.0
            elif drawdown_from_high <= -trailing_stop_pct:
                position = 0
                entry_price = 0.0
                highest_price = 0.0
            elif close_price < ema9:
                position = 0
                entry_price = 0.0
                highest_price = 0.0
            elif ema9 < ema21:
                position = 0
                entry_price = 0.0
                highest_price = 0.0
            elif close_price < vwap:
                position = 0
                entry_price = 0.0
                highest_price = 0.0

        positions.append(position)
        entry_prices.append(entry_price)
        highest_prices.append(highest_price)

    data["Position"] = pd.Series(positions, index=data.index).shift(1).fillna(0)
    data["EntryPriceLive"] = pd.Series(entry_prices, index=data.index)
    data["HighestPriceLive"] = pd.Series(highest_prices, index=data.index)

    current_position = int(data["Position"].iloc[-1])
    last_close = float(data["Close"].iloc[-1])
    live_entry = float(data["EntryPriceLive"].iloc[-1]) if current_position == 1 else 0.0
    live_highest = float(data["HighestPriceLive"].iloc[-1]) if current_position == 1 else 0.0

    stop_loss_price = live_entry * (1 - stop_loss_pct) if current_position == 1 else 0.0
    take_profit_price = live_entry * (1 + take_profit_pct) if current_position == 1 else 0.0
    trailing_exit_price = live_highest * (1 - trailing_stop_pct) if current_position == 1 else 0.0

    return {
        "symbol": symbol,
        "position": current_position,
        "last_close": round(last_close, 2),
        "entry_price": round(live_entry, 2),
        "stop_loss": round(stop_loss_price, 2),
        "take_profit": round(take_profit_price, 2),
        "trailing_exit": round(trailing_exit_price, 2)
    }

# =========================
# Main Monitor Loop
# =========================
def monitor():
    print("Bot started. Monitoring every 60 seconds...")
    state = load_state()

    # أول تشغيل: لو ما فيه ملف حالة، نسجل الحالة فقط بدون إرسال
    if not state:
        for symbol in symbols:
            try:
                result = analyze_symbol(symbol)
                if result:
                    state[symbol] = result
                    print(f"Initialized {symbol}: position={result['position']}")
            except Exception as e:
                print(f"Init error with {symbol}: {e}")
        save_state(state)
        print("Initial state saved. Waiting for new events only.")

    while True:
        try:
            state = load_state()

            for symbol in symbols:
                try:
                    result = analyze_symbol(symbol)
                    if result is None:
                        continue

                    old = state.get(symbol, {
                        "position": 0,
                        "last_close": 0.0,
                        "entry_price": 0.0,
                        "stop_loss": 0.0,
                        "take_profit": 0.0,
                        "trailing_exit": 0.0
                    })

                    old_pos = int(old.get("position", 0))
                    new_pos = int(result["position"])

                    # دخول جديد
                    if old_pos == 0 and new_pos == 1:
                        msg = (
                            f"🔥 NEW BUY SIGNAL\n\n"
                            f"📊 Symbol: {result['symbol']}\n"
                            f"💰 Entry: {result['last_close']}\n"
                            f"🛑 Stop Loss: {result['stop_loss']}\n"
                            f"🎯 Take Profit: {result['take_profit']}\n"
                            f"📉 Trailing Exit: {result['trailing_exit']}"
                        )
                        send_telegram(msg)
                        print(f"BUY sent for {symbol}")

                    # إغلاق صفقة
                    elif old_pos == 1 and new_pos == 0:
                        msg = (
                            f"✅ TRADE CLOSED\n\n"
                            f"📊 Symbol: {result['symbol']}\n"
                            f"💵 Exit Price: {result['last_close']}"
                        )
                        send_telegram(msg)
                        print(f"EXIT sent for {symbol}")

                    state[symbol] = result

                except Exception as e:
                    print(f"Error with {symbol}: {e}")

            save_state(state)
            time.sleep(60)

        except KeyboardInterrupt:
            print("Stopped by user.")
            break
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    monitor()
