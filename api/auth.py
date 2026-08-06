import hmac
import hashlib
import json
import urllib.parse
from fastapi import HTTPException, Header
import os

def validate_telegram_init_data(init_data: str, bot_token: str) -> dict:
    """
    Валідує initData згідно зі специфікацією Telegram WebApp.
    Повертає словник даних користувача у разі успіху або викликає ValueError.
    """
    if not init_data:
        raise ValueError("Init data is empty")

    parsed_data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    if "hash" not in parsed_data:
        raise ValueError("Hash missing in init data")

    received_hash = parsed_data.pop("hash")
    
    # Формуємо data_check_string, відсортувавши ключі за алфавітом
    data_check_lines = [f"{k}={v}" for k, v in sorted(parsed_data.items())]
    data_check_string = "\n".join(data_check_lines)

    # HMAC-SHA256 ключ з "WebAppData" та бот-токеном
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Invalid init data signature")

    user_str = parsed_data.get("user")
    if not user_str:
        raise ValueError("User data missing in init data")

    try:
        user_data = json.loads(user_str)
        return user_data
    except Exception as e:
        raise ValueError(f"Failed to parse user JSON: {e}")


async def get_current_user(x_telegram_init_data: str = Header(None, alias="X-Telegram-Init-Data")) -> int:
    """
    FastAPI dependency для отримання та перевірки telegram user_id із заголовка X-Telegram-Init-Data.
    Також підтримує режим розробки, якщо встановлено DEV_TELEGRAM_USER_ID у середовищі.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    # Для DEV-тестування якщо підпис відсутній
    dev_user_id = os.getenv("DEV_TELEGRAM_USER_ID")
    if not x_telegram_init_data and dev_user_id:
        return int(dev_user_id)

    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="X-Telegram-Init-Data header missing")

    if not bot_token:
        raise HTTPException(status_code=500, detail="TELEGRAM_BOT_TOKEN is not configured")

    try:
        user_data = validate_telegram_init_data(x_telegram_init_data, bot_token)
        return int(user_data["id"])
    except ValueError as err:
        raise HTTPException(status_code=403, detail=str(err))
