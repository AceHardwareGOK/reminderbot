from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

# Main Menu Keyboard Layout
MAIN_KEYBOARD = [
    ['➕ Створити нагадування'],
    ['📋 Мої нагадування', '⏸ Відкласти всі'],
    ['🗑 Видалити нагадування'],
]
MAIN_MARKUP = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)

CANCEL_KEYBOARD = [['🏠 Скасувати']]
CANCEL_MARKUP = ReplyKeyboardMarkup(CANCEL_KEYBOARD, resize_keyboard=True)

def build_dashboard_keyboard(task_id: int, current_index: int, total_count: int) -> InlineKeyboardMarkup:
    """Build interactive dashboard keyboard with pagination and action buttons."""
    buttons = []
    
    # Action Row
    action_row = [
        InlineKeyboardButton("✏️ Редагувати", callback_data=f"edit_{task_id}", api_kwargs={'style': 'primary'}),
        InlineKeyboardButton("🗑 Видалити", callback_data=f"delete_{task_id}", api_kwargs={'style': 'danger'})
    ]
    buttons.append(action_row)
    
    # Pagination Row (only if total_count > 1)
    if total_count > 1:
        prev_idx = (current_index - 1) % total_count
        next_idx = (current_index + 1) % total_count
        
        nav_row = [
            InlineKeyboardButton("◀️ Назад", callback_data=f"page_{prev_idx}"),
            InlineKeyboardButton(f"📌 {current_index + 1}/{total_count}", callback_data="noop"),
            InlineKeyboardButton("Вперед ▶️", callback_data=f"page_{next_idx}")
        ]
        buttons.append(nav_row)
        
    return InlineKeyboardMarkup(buttons)

def build_reminder_keyboard(task_id: int, reminder_code: str) -> InlineKeyboardMarkup:
    """Build reminder notification keyboard with styled buttons."""
    buttons = [
        [
            InlineKeyboardButton(
                "✅ Виконано",
                callback_data=f"done_{task_id}_{reminder_code}",
                api_kwargs={'style': 'success'}
            ),
            InlineKeyboardButton(
                "⏸ Відкласти",
                callback_data=f"snooze_{task_id}_{reminder_code}",
                api_kwargs={'style': 'primary'}
            )
        ]
    ]
    return InlineKeyboardMarkup(buttons)
