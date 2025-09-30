from __future__ import annotations

import os
from typing import Optional

import requests

# Expose the four environment-driven constants for compatibility/usability
AUTO_BOT = os.getenv("TCAutoBotToken")
AUTO_CHAT = os.getenv("TCAutoChatID")
LOG_BOT = os.getenv("TCLogBotToken")
LOG_CHAT = os.getenv("TCLogBotChatID")

__all__ = [
    "AUTO_BOT",
    "AUTO_CHAT",
    "LOG_BOT",
    "LOG_CHAT",
    "send_message",
]


def send_message(message: str, bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
    bot = bot_token or AUTO_BOT or LOG_BOT
    chat = chat_id or AUTO_CHAT or LOG_CHAT
    if not bot or not chat:
        return
    url = f"https://api.telegram.org/bot{bot}/sendMessage"
    payload = {"chat_id": chat, "text": message}
    try:
        resp = requests.post(url, data=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[telegram] failed to send: {e}")
