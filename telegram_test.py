import os
import requests

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

    r = requests.post(url, data=payload, timeout=15)
    print("Telegram status:", r.status_code)
    print("Telegram response:", r.text)

def run_once():
    print("Bot started...")
    send_telegram("✅ GitHub Actions test message")
    print("Finished")

if __name__ == "__main__":
    run_once()
