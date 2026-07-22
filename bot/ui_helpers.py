import re
from typing import Dict, List, Optional
from telegram.helpers import escape_markdown
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

def escape_md(text: Optional[str]) -> str:
    """Safely escape text for Telegram MarkdownV2."""
    if not text:
        return ""
    return escape_markdown(str(text), version=2)

def get_task_type_str(task: Dict) -> str:
    """Return formatted task type label."""
    return "✅ Одноразове" if task.get('is_one_time') else "🔁 Повторюване"

def format_progress_header(step: int, total_steps: int, step_name: str) -> str:
    """Generate visual progress bar header for wizard steps."""
    filled = "🟩" * step
    empty = "⬜" * (total_steps - step)
    bar = f"{filled}{empty}"
    return f"{bar} *Крок {step} з {total_steps}:* {escape_md(step_name)}"

def format_wizard_step(step: int, data: dict) -> str:
    """Render Rich MarkdownV2 text for Single-Message Wizard steps."""
    desc = escape_md(data.get('description', 'Не вказано'))
    
    if step == 1:
        return (
            f"➕ *Створення нагадування*\n\n"
            f"{format_progress_header(1, 4, 'Опис завдання')}\n\n"
            f"> ✍️ *Введи опис або текст нагадування у чат:* \n\n"
            f"💡 _Наприклад: Пройти рев'ю коду, Купити молоко, Взяти ліки_"
        )
    
    elif step == 2:
        return (
            f"➕ *Створення нагадування*\n\n"
            f"{format_progress_header(2, 4, 'Вибір днів / типу')}\n"
            f"> 📌 *Опис:* {desc}\n\n"
            f"📅 *Обери дні тижня або тип нагадування нижче:*"
        )
        
    elif step == 3:
        days = data.get('days', [])
        is_one_time = data.get('is_one_time', False)
        everyday = data.get('everyday', False)
        one_time_date = data.get('one_time_date')
        
        if one_time_date:
            days_str = escape_md(f"Дата: {one_time_date}")
        elif is_one_time:
            days_str = escape_md("Одноразове")
        elif everyday or len(days) == 7:
            days_str = escape_md("Щодня")
        elif days:
            from core.scheduler import DayOfWeek
            day_names = [DayOfWeek.from_index(d).short.upper() for d in days]
            days_str = escape_md(', '.join(day_names))
        else:
            days_str = escape_md("Не обрано")
            
        times = data.get('times', [])
        times_str = escape_md(', '.join(times)) if times else escape_md("Не вказано")
            
        return (
            f"➕ *Створення нагадування*\n\n"
            f"{format_progress_header(3, 4, 'Вибір часу')}\n"
            f"> 📌 *Опис:* {desc}\n"
            f"📅 *Розклад:* {days_str}\n"
            f"⏰ *Обрані часи:* `{times_str}`\n\n"
            f"⏰ *Обери популярні години нижче або введи свій час у чат \\(наприклад, 09:30, 18:00\\):*"
        )
        
    elif step == 4:
        days = data.get('days', [])
        is_one_time = data.get('is_one_time', False)
        everyday = data.get('everyday', False)
        one_time_date = data.get('one_time_date')
        
        if one_time_date:
            days_str = escape_md(f"Дата: {one_time_date}")
        elif everyday or len(days) == 7:
            days_str = escape_md("Щодня")
        elif days:
            from core.scheduler import DayOfWeek
            day_names = [DayOfWeek.from_index(d).full for d in days]
            days_str = escape_md(', '.join(day_names))
        else:
            days_str = escape_md("Не вказано")
            
        task_type = escape_md("✅ Одноразове" if is_one_time else "🔁 Повторюване")
        times = data.get('times', [])
        times_str = escape_md(', '.join(times)) if times else escape_md("Не вказано")
        
        interval = data.get('interval_minutes', 0)
        interval_str = escape_md("без повторень" if interval == 0 else f"кожні {interval} хв")
        
        return (
            f"➕ *Створення нагадування*\n\n"
            f"{format_progress_header(4, 4, 'Перевірка та збереження')}\n\n"
            f"> 📌 *Опис:* {desc}\n"
            f"🏷️ *Тип:* {task_type}\n"
            f"📅 *Розклад:* {days_str}\n"
            f"⏰ *Час:* `{times_str}`\n"
            f"⏱️ *Інтервал:* `{interval_str}`\n\n"
            f"⏱️ *Обери популярний інтервал нижче або введи свій у чат \\(наприклад, 45, 90 чи 1:30\\):*\n"
            f"✨ _Після цього натисни кнопку збереження нижче\\!_"
        )

def build_wiz_days_keyboard(selected_days: list, is_one_time: bool = False, everyday: bool = False) -> InlineKeyboardMarkup:
    """Build interactive Inline Keyboard for selecting days in wizard."""
    days_map = [("Пн", 0), ("Вт", 1), ("Ср", 2), ("Чт", 3), ("Пт", 4), ("Сб", 5), ("Нд", 6)]
    
    row1, row2 = [], []
    for label, idx in days_map[:4]:
        mark = "✅ " if (idx in selected_days and not is_one_time) else ""
        row1.append(InlineKeyboardButton(f"{mark}{label}", callback_data=f"wizday_{idx}"))
    for label, idx in days_map[4:]:
        mark = "✅ " if (idx in selected_days and not is_one_time) else ""
        row2.append(InlineKeyboardButton(f"{mark}{label}", callback_data=f"wizday_{idx}"))
        
    everyday_mark = "✅ " if everyday else ""
    onetime_mark = "✅ " if is_one_time else ""
    
    row_mode = [
        InlineKeyboardButton(f"{everyday_mark}🔁 Щодня", callback_data="wizday_everyday"),
        InlineKeyboardButton(f"{onetime_mark}🏁 Одноразове", callback_data="wizday_onetime")
    ]
    
    row_actions = [
        InlineKeyboardButton("◀️ Назад", callback_data="wizback_1"),
        InlineKeyboardButton("✅ Далі (Час)", callback_data="wizday_confirm", api_kwargs={'style': 'primary'}),
        InlineKeyboardButton("❌ Скасувати", callback_data="wiz_cancel", api_kwargs={'style': 'danger'})
    ]
    
    return InlineKeyboardMarkup([row1, row2, row_mode, row_actions])

def build_wiz_times_keyboard(selected_times: list) -> InlineKeyboardMarkup:
    """Build Inline Keyboard for quick time selection."""
    presets = ["08:00", "09:00", "12:00", "15:00", "18:00", "21:00"]
    row1, row2 = [], []
    for t in presets[:3]:
        mark = "✅ " if t in selected_times else ""
        row1.append(InlineKeyboardButton(f"{mark}{t}", callback_data=f"wiztime_{t}"))
    for t in presets[3:]:
        mark = "✅ " if t in selected_times else ""
        row2.append(InlineKeyboardButton(f"{mark}{t}", callback_data=f"wiztime_{t}"))
        
    row_actions = [
        InlineKeyboardButton("◀️ Назад", callback_data="wizback_2"),
        InlineKeyboardButton("✅ Далі (Інтервал)", callback_data="wiztime_confirm", api_kwargs={'style': 'primary'}),
        InlineKeyboardButton("❌ Скасувати", callback_data="wiz_cancel", api_kwargs={'style': 'danger'})
    ]
    return InlineKeyboardMarkup([row1, row2, row_actions])

def build_wiz_interval_keyboard(current_interval: int = 0) -> InlineKeyboardMarkup:
    """Build Inline Keyboard for interval and final save."""
    opts = [(0, "Без повторів"), (15, "15 хв"), (30, "30 хв"), (60, "1 год")]
    standard_vals = {val for val, _ in opts}
    
    row = []
    for val, label in opts:
        mark = "✅ " if current_interval == val else ""
        row.append(InlineKeyboardButton(f"{mark}{label}", callback_data=f"wizint_{val}"))
        
    rows = [row]
    
    if current_interval not in standard_vals and current_interval > 0:
        custom_row = [
            InlineKeyboardButton(f"✅ Власний: {current_interval} хв", callback_data=f"wizint_{current_interval}")
        ]
        rows.append(custom_row)
        
    row_save = [
        InlineKeyboardButton("◀️ Назад", callback_data="wizback_3"),
        InlineKeyboardButton("🚀 Зберегти!", callback_data="wiz_save", api_kwargs={'style': 'primary'}),
        InlineKeyboardButton("❌ Скасувати", callback_data="wiz_cancel", api_kwargs={'style': 'danger'})
    ]
    rows.append(row_save)
    return InlineKeyboardMarkup(rows)

def format_task_card(task: Dict, title: str = "📝 *Завдання*") -> str:
    """Format task dictionary into a sleek MarkdownV2 card."""
    from core.scheduler import DayOfWeek
    
    desc = escape_md(task.get('description', ''))
    task_type = escape_md(get_task_type_str(task))
    
    one_time_date = task.get('one_time_date')
    if one_time_date:
        days_str = escape_md(f"Дата: {one_time_date}")
    else:
        days = task.get('days', [])
        if days:
            day_names = [DayOfWeek.from_index(d).full for d in days]
            days_str = escape_md(', '.join(day_names))
        else:
            days_str = escape_md('Не вказано')
            
    times = task.get('times', [])
    times_str = escape_md(', '.join(times)) if times else escape_md('Не вказано')
    
    interval = task.get('interval_minutes', 0)
    if interval == 0:
        interval_str = escape_md("без повторень")
    else:
        interval_str = escape_md(f"кожні {interval} хв")
        
    card = (
        f"{title}\n"
        f"> 📌 *Опис:* {desc}\n\n"
        f"🏷️ *Тип:* {task_type}\n"
        f"📅 *Розклад:* {days_str}\n"
        f"⏰ *Час:* `{times_str}`\n"
        f"⏱️ *Інтервал:* `{interval_str}`"
    )
    return card

def format_reminder_notification(task: Dict, reminder_time: str) -> str:
    """Format notification message when reminder triggers."""
    desc = escape_md(task.get('description', ''))
    time_esc = escape_md(reminder_time)
    
    card = (
        f"🔔 *НАГАДУВАННЯ*\n\n"
        f"> 📝 *{desc}*\n\n"
        f"🕒 *Час спрацювання:* `{time_esc}`\n\n"
        f"💡 _Познач як виконане або відклади, коли будеш готовий:_"
    )
    return card
