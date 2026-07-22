import re
from typing import Dict, List, Optional
from telegram.helpers import escape_markdown

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

def format_task_card(task: Dict, title: str = "📝 *Завдання*") -> str:
    """Format task dictionary into a sleek MarkdownV2 card."""
    from bot.handlers import DayOfWeek  # Lazy import if needed or use index mapping
    
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
