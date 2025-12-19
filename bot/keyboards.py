from telegram import ReplyKeyboardMarkup

# Keyboard layouts
MAIN_KEYBOARD = [
    ['➕ Створити нагадування'],
    ['📋 Мої нагадування'],
    ['🗑 Видалити нагадування']
]
MAIN_MARKUP = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)

CANCEL_KEYBOARD = [['🏠 Скасувати']]
CANCEL_MARKUP = ReplyKeyboardMarkup(CANCEL_KEYBOARD, resize_keyboard=True)
