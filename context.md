# ReminderBot — Контекст проєкту

## Опис проєкту
Telegram-бот для створення, керування та відстеження нагадувань з підтримкою інтервалів, разових та повторюваних завдань, збереженням у SQLite (aiosqlite) та розкладом через APScheduler.

## Поточний стан
- **Поточна гілка Git:** `feature/rich-ui`
- **Основні бібліотеки:** `python-telegram-bot==22.5`, `APScheduler==3.11.0`, `aiosqlite==0.19.0`
- **Реалізовано:** 
  1. **Single-Message Inline Wizard:** Весь покроковий процес створення нагадувань тепер відбувається в **одному-єдиному повідомленні**, яке динамічно оновлюється (`edit_message_text`) з використанням Inline-кнопок, `MarkdownV2` та автоматичного підчищення повідомлень користувача з чату!
  2. **Interactive Dashboard:** Зручна карусельна пагінація (`◀️ 1/N ▶️`) списку нагадувань.
  3. **Багфікс одноразових завдань:** Виправлено обробку декількох часів для одноразових нагадувань.

## Що зроблено (Останні зміни)
- **`bot/ui_helpers.py`:**
  - Додано `format_wizard_step()` для візуального відображення кроків створення нагадувань.
  - Додано створення Inline-клавіатур `build_wiz_days_keyboard()`, `build_wiz_times_keyboard()`, `build_wiz_interval_keyboard()`.
- **`bot/handlers.py`:**
  - Переписано `create_reminder_start`, `get_description`, `get_days`, `get_times`, `get_interval` та реалізовано `handle_wizard_callback`.
- **`main.py`:**
  - Оновлено `conv_handler` для підтримки паттернів `^wiz`.

## Наступні кроки
- Перезапустити тестового бота й протестувати створення через один Inline Wizard.
- Злити гілку `feature/rich-ui` у `main`.
