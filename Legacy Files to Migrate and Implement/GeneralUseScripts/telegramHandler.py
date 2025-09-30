import os
import requests

# —— Bot tokens & chat IDs pulled once on import ——
AUTO_BOT = os.getenv("TCAutoBotToken")
AUTO_CHAT = os.getenv("TCAutoChatID")
LOG_BOT  = os.getenv("TCLogBotToken")
LOG_CHAT = os.getenv("TCLogBotChatID")

def send_telegram_message(message: str, bot_token: str, chat_id: str) -> None:
    """
    Sends a message to Telegram via Bot API.
    If credentials are missing, silently skips.
    """
    if not bot_token or not chat_id:
        # credentials not set
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        resp = requests.post(url, data=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        # you could log this locally if you want
        print(f"[telegram_utils] failed to send: {e}")
