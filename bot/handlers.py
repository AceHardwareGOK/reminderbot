import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

from core.config import TIMEZONE
from core.database import DatabaseManager
from core.scheduler import ReminderManager, DayOfWeek
from utils.validators import Validator
from .states import ConversationState
from .keyboards import MAIN_MARKUP, CANCEL_MARKUP, MAIN_KEYBOARD, build_dashboard_keyboard
from .ui_helpers import (
    escape_md, format_task_card, format_progress_header, 
    format_reminder_notification, get_task_type_str
)

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)

class BotHandlers:
    """Container for bot command and conversation handlers"""
    
    def __init__(self, db: DatabaseManager, reminder_manager: ReminderManager):
        self.db = db
        self.reminder_manager = reminder_manager
        self.validator = Validator()
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        if not user or not update.message:
            return
        
        logger.info(f"User {user.id} started bot")
        
        await update.message.reply_text(
            f"Привіт, {user.first_name}! 👋\n\n"
            "Я твій особистий бот-нагадувач. Допоможу тобі пам'ятати про важливі справи!\n\n"
            "Використовуй кнопки нижче для навігації:",
            reply_markup=MAIN_MARKUP
        )
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel current operation"""
        if not update.message:
            return
        
        # Clean up user data
        if context.user_data:
            context.user_data.clear()
        
        if update.effective_user:
            user_id = update.effective_user.id
            if user_id in self.reminder_manager.user_day_selections:
                del self.reminder_manager.user_day_selections[user_id]
        
        await update.message.reply_text(
            "❌ Створення нагадування скасовано.",
            reply_markup=MAIN_MARKUP
        )
        return ConversationHandler.END

    async def debug_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show server time debug info"""
        if not update.message:
            return
            
        server_now = datetime.now()
        utc_now = datetime.now(ZoneInfo("UTC"))
        tz_now = datetime.now(TZ)
        
        await update.message.reply_text(
            f"🕒 *Час на сервері*\n\n"
            f"📅 *Server Local:* `{escape_md(server_now)}`\n"
            f"🌍 *UTC:* `{escape_md(utc_now)}`\n"
            f"🇺🇦 *Configured \\({escape_md(TIMEZONE)}\\):* `{escape_md(tz_now)}`\n"
            f"ℹ️ *ZoneInfo:* `{escape_md(TZ)}`",
            parse_mode='MarkdownV2'
        )

    async def refresh_scheduler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Force reschedule all tasks from DB"""
        if not update.message or not update.effective_user:
            return
            
        try:
            # Get all active tasks
            # We need to access db directly or add method to manager?
            # Manager doesn't have method to get all tasks, db does.
            # But we want ALL tasks for ALL users to fix system-wide issue?
            # Or just for current user? Let's do current user first to be safe, 
            # but usually refresh is admin command. Given context, user is likely admin/sole user.
            
            user_id = update.effective_user.id
            
            # Re-fetch tasks
            tasks = await self.db.get_user_tasks(user_id)
            
            count = 0
            for task in tasks:
                # Cancel existing
                self.reminder_manager.cancel_task(user_id, task['task_id'])
                # Schedule new
                self.reminder_manager.schedule_task(task)
                count += 1
                
            await update.message.reply_text(
                f"✅ Оновлено планувальник.\n"
                f"Перезаплановано завдань: {count}\n\n"
                f"Тепер вони мають використовувати коректний часовий пояс."
            )
            
        except Exception as e:
            logger.error(f"Error refreshing scheduler: {e}")
            await update.message.reply_text("❌ Помилка оновлення.")

    # ==================== CREATE REMINDER FLOW ====================
    
    async def create_reminder_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start reminder creation"""
        if not update.message:
            return
        
        await update.message.reply_text(
            f"➕ *Створення нового нагадування*\n\n"
            f"{format_progress_header(1, 4, 'Опис завдання')}\n\n"
            f"📝 Введи опис або текст завдання:",
            parse_mode='MarkdownV2',
            reply_markup=CANCEL_MARKUP
        )
        return ConversationState.DESCRIBING_TASK.value
    
    async def get_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get task description"""
        if not update.message or not update.message.text:
            return ConversationHandler.END
        
        description = update.message.text.strip()
        
        if description == '🏠 Скасувати':
            return await self.cancel(update, context)
        
        if not description:
            await update.message.reply_text(
                "⚠️ *Опис не може бути порожнім\\.* Спробуй ще раз:",
                parse_mode='MarkdownV2',
                reply_markup=CANCEL_MARKUP
            )
            return ConversationState.DESCRIBING_TASK.value
        
        context.user_data['description'] = description
        
        # Initialize day selection
        if update.effective_user:
            self.reminder_manager.user_day_selections[update.effective_user.id] = []
        
        days_keyboard = [
            ['пн', 'вт', 'ср'],
            ['чт', 'пт', 'сб'],
            ['нд'],
            ['щодня', 'одноразове'],
            ['✅ Підтвердити', '🏠 Скасувати']
        ]
        
        await update.message.reply_text(
            f"{format_progress_header(2, 4, 'Обираємо дні')}\n\n"
            f"📅 *Обери дні для нагадування:*\n"
            f"• Натискай на дні для вибору/скасування\n"
            f"• Натисни 'щодня' для щоденних\n"
            f"• Натисни 'одноразове' для разового\n"
            f"• Натисни '✅ Підтвердити', коли закінчиш",
            parse_mode='MarkdownV2',
            reply_markup=ReplyKeyboardMarkup(days_keyboard, resize_keyboard=True)
        )
        return ConversationState.CHOOSING_DAYS.value

    async def get_days(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle day selection"""
        if not update.message or not update.message.text or not update.effective_user:
            return ConversationHandler.END
        
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        if text == '🏠 Скасувати':
            return await self.cancel(update, context)
        
        # Handle one-time task
        if text == 'одноразове':
            context.user_data['is_one_time'] = True
            
            # Show options for one-time reminder: day of week or specific date
            now = datetime.now(TZ)
            current_day = now.weekday()
            
            # Get next occurrence of each day of week
            next_days = []
            seen_days = set()
            i = 0
            while len(seen_days) < 7 and i < 14:  # Limit to 14 days ahead
                day_index = (current_day + i) % 7
                if day_index not in seen_days:
                    seen_days.add(day_index)
                    day = DayOfWeek.from_index(day_index)
                    if day:
                        if i == 0:
                            day_label = f"{day.full} (сьогодні)"
                        elif i == 1:
                            day_label = f"{day.full} (завтра)"
                        else:
                            # Plural form for days
                            if i % 10 == 2 or i % 10 == 3 or i % 10 == 4:
                                day_label = f"{day.full} (через {i} дні)"
                            else:
                                day_label = f"{day.full} (через {i} днів)"
                        next_days.append((day_index, day_label))
                i += 1
            
            day_keyboard = []
            for i in range(0, len(next_days), 2):
                row = [next_days[i][1]]
                if i + 1 < len(next_days):
                    row.append(next_days[i + 1][1])
                day_keyboard.append(row)
            
            day_keyboard.append(['📅 Вказати конкретну дату'])
            day_keyboard.append(['🏠 Скасувати'])
            
            await update.message.reply_text(
                "📅 Одноразове нагадування\n\n"
                "Обери найближчий день тижня або вкажи конкретну дату:",
                reply_markup=ReplyKeyboardMarkup(day_keyboard, resize_keyboard=True)
            )
            
            # Store day options for reference
            context.user_data['one_time_day_options'] = {label: idx for idx, label in next_days}
            
            return ConversationState.CHOOSING_ONE_TIME_DATE.value
        
        # Handle everyday selection
        if text == 'щодня':
            context.user_data['everyday'] = True
            await update.message.reply_text(
                "✅ Обрано щоденні нагадування.\n"
                "Натисни '✅ Підтвердити', щоб продовжити."
            )
            return ConversationState.CHOOSING_DAYS.value
        
        # Handle confirmation
        if text == '✅ Підтвердити':
            selected_days = self.reminder_manager.user_day_selections.get(user_id, [])
            
            if context.user_data.get('everyday'):
                selected_days = list(range(7))
            
            is_one_time = context.user_data.get('is_one_time', False)
            
            if not selected_days and not is_one_time and not context.user_data.get('everyday'):
                await update.message.reply_text(
                    "⚠️ Будь ласка, обери хоча б один день."
                )
                return ConversationState.CHOOSING_DAYS.value
            
            context.user_data['days'] = selected_days
            
            await update.message.reply_text(
                "⏰ Введи час для нагадувань (24-годинний формат, наприклад, 09:30)\n"
                "Розділяй кілька часів комами (наприклад, 09:30, 14:15, 18:00)",
                reply_markup=CANCEL_MARKUP
            )
            return ConversationState.CHOOSING_TIMES.value
        
        # Handle individual day selection
        day = DayOfWeek.from_short(text)
        if day:
            if user_id not in self.reminder_manager.user_day_selections:
                self.reminder_manager.user_day_selections[user_id] = []
            
            current = self.reminder_manager.user_day_selections[user_id]
            if day.index in current:
                current.remove(day.index)
            else:
                current.append(day.index)
            
            current.sort()
            
            if current:
                day_names = [DayOfWeek.from_index(i).full for i in current]
                feedback = f"✅ Обрані дні: {', '.join(day_names)}"
            else:
                feedback = "Ще не обрано жодного дня."
            
            await update.message.reply_text(feedback)
        
        return ConversationState.CHOOSING_DAYS.value

    async def get_one_time_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle one-time reminder date/day selection"""
        if not update.message or not update.message.text or not update.effective_user:
            return ConversationHandler.END
        
        text = update.message.text.strip()
        
        if text == '🏠 Скасувати':
            return await self.cancel(update, context)
        
        # Check if specific date was selected
        if text == '📅 Вказати конкретну дату':
            await update.message.reply_text(
                "📅 Введи дату і час для нагадування\n\n"
                "Формат: ДД.ММ.РРРР ГГ:ХХ\n"
                "Приклади:\n"
                "• 25.12.2024 16:00\n"
                "• 01.01.2025 09:30\n\n"
                "Або просто дату (час вкажеш далі):\n"
                "• 25.12.2024",
                reply_markup=CANCEL_MARKUP
            )
            context.user_data['waiting_for_date_input'] = True
            return ConversationState.CHOOSING_ONE_TIME_DATE.value
        
        # Check if waiting for date input
        if context.user_data.get('waiting_for_date_input'):
            try:
                # Try to parse date with time
                if len(text) > 10:  # Contains time
                    # Format: DD.MM.YYYY HH:MM
                    target_datetime = datetime.strptime(text, '%d.%m.%Y %H:%M')
                    context.user_data['one_time_date'] = target_datetime.strftime('%Y-%m-%d %H:%M')
                    context.user_data['waiting_for_date_input'] = False
                    # Skip time selection since time is already included
                    context.user_data['times'] = [target_datetime.strftime('%H:%M')]
                    context.user_data['days'] = []  # No day needed for specific date
                    
                    # Go directly to interval selection
                    interval_keyboard = [
                        ['не повторювати'],
                        ['5 хвилин', '10 хвилин'],
                        ['15 хвилин', '30 хвилин'],
                        ['1 година', '2 години'],
                        ['Власний інтервал'],
                        ['🏠 Скасувати']
                    ]
                    
                    await update.message.reply_text(
                        f"✅ Дата встановлена: {target_datetime.strftime('%d.%m.%Y %H:%M')}\n\n"
                        "⏱️ Як часто мені нагадувати, якщо ти не позначиш як виконане?",
                        reply_markup=ReplyKeyboardMarkup(interval_keyboard, resize_keyboard=True)
                    )
                    return ConversationState.CHOOSING_INTERVAL.value
                else:
                    # Format: DD.MM.YYYY (only date)
                    target_date = datetime.strptime(text, '%d.%m.%Y')
                    # Check if date is in the past
                    if target_date.date() < datetime.now(TZ).date():
                        await update.message.reply_text(
                            "⚠️ Дата не може бути в минулому. Введи дату ще раз:",
                            reply_markup=CANCEL_MARKUP
                        )
                        return ConversationState.CHOOSING_ONE_TIME_DATE.value
                    
                    context.user_data['one_time_date'] = target_date.strftime('%Y-%m-%d')
                    context.user_data['waiting_for_date_input'] = False
                    context.user_data['days'] = []  # No day needed for specific date
                    
                    await update.message.reply_text(
                        f"✅ Дата встановлена: {target_date.strftime('%d.%m.%Y')}\n\n"
                        "⏰ Введи час для нагадування (24-годинний формат, наприклад, 16:00):",
                        reply_markup=CANCEL_MARKUP
                    )
                    return ConversationState.CHOOSING_TIMES.value
            except ValueError:
                await update.message.reply_text(
                    "⚠️ Неправильний формат дати. Спробуй ще раз:\n\n"
                    "Формат: ДД.ММ.РРРР ГГ:ХХ або ДД.ММ.РРРР\n"
                    "Приклад: 25.12.2024 16:00",
                    reply_markup=CANCEL_MARKUP
                )
                return ConversationState.CHOOSING_ONE_TIME_DATE.value
        
        # Check if day of week was selected
        day_options = context.user_data.get('one_time_day_options', {})
        if text in day_options:
            selected_day = day_options[text]
            context.user_data['days'] = [selected_day]
            context.user_data['one_time_date'] = None
            
            day = DayOfWeek.from_index(selected_day)
            await update.message.reply_text(
                f"✅ Обрано: {day.full if day else 'день'}\n\n"
                "⏰ Введи час для нагадування (24-годинний формат, наприклад, 16:00):",
                reply_markup=CANCEL_MARKUP
            )
            return ConversationState.CHOOSING_TIMES.value
        
        # Unknown input
        await update.message.reply_text(
            "⚠️ Будь ласка, обери день тижня або вкажи конкретну дату.",
            reply_markup=CANCEL_MARKUP
        )
        return ConversationState.CHOOSING_ONE_TIME_DATE.value

    async def get_times(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get and validate times"""
        if not update.message or not update.message.text:
            return ConversationHandler.END
        
        text = update.message.text.strip()
        
        if text == '🏠 Скасувати':
            return await self.cancel(update, context)
        
        valid_times, invalid_times = self.validator.parse_times(text)
        
        if invalid_times:
            await update.message.reply_text(
                f"⚠️ Неправильний формат часу: {', '.join(invalid_times)}\n"
                "Будь ласка, використовуй 24-годинний формат (ГГ:ХХ)",
                reply_markup=CANCEL_MARKUP
            )
            return ConversationState.CHOOSING_TIMES.value
        
        if not valid_times:
            await update.message.reply_text(
                "⚠️ Будь ласка, введи хоча б один час.",
                reply_markup=CANCEL_MARKUP
            )
            return ConversationState.CHOOSING_TIMES.value
        
        context.user_data['times'] = valid_times
        
        interval_keyboard = [
            ['не повторювати'],
            ['5 хвилин', '10 хвилин'],
            ['15 хвилин', '30 хвилин'],
            ['1 година', '2 години'],
            ['Власний інтервал'],
            ['🏠 Скасувати']
        ]
        
        await update.message.reply_text(
            "⏱️ Як часто мені нагадувати, якщо ти не позначиш як виконане?",
            reply_markup=ReplyKeyboardMarkup(interval_keyboard, resize_keyboard=True)
        )
        return ConversationState.CHOOSING_INTERVAL.value

    async def get_interval(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get reminder interval"""
        if not update.message or not update.message.text or not update.effective_user:
            return ConversationHandler.END
        
        text = update.message.text.strip()
        
        if text == '🏠 Скасувати':
            return await self.cancel(update, context)
        
        if text == 'Власний інтервал':
            await update.message.reply_text(
                "⏱️ Введи інтервал (у хвилинах, наприклад 90, або години:хвилини, наприклад 1:30):",
                reply_markup=CANCEL_MARKUP
            )
            return ConversationState.CHOOSING_INTERVAL.value
        
        # Parse interval
        interval_map = {
            '5 хвилин': 5, '10 хвилин': 10, '15 хвилин': 15,
            '30 хвилин': 30, '1 година': 60, '2 години': 120
        }
        
        # Handle interval
        if text == 'не повторювати':
            interval_minutes = 0
        else:
            interval_minutes = interval_map.get(text)
            
            if interval_minutes is None:
                interval_minutes = self.validator.parse_interval(text)
                if interval_minutes is None:
                    await update.message.reply_text(
                        "⚠️ Будь ласка, введи інтервал (наприклад 90 або 1:30).",
                        reply_markup=CANCEL_MARKUP
                    )
                    return ConversationState.CHOOSING_INTERVAL.value
        
        if not self.validator.validate_interval(interval_minutes):
            await update.message.reply_text(
                "⚠️ Інтервал має бути від 1 до 1440 хвилин.",
                reply_markup=CANCEL_MARKUP
            )
            return ConversationState.CHOOSING_INTERVAL.value
        
        # Save task
        user_id = update.effective_user.id
        description = context.user_data.get('description', '')
        days = context.user_data.get('days', [])
        times = context.user_data.get('times', [])
        is_one_time = context.user_data.get('is_one_time', False)
        one_time_date = context.user_data.get('one_time_date')
        
        try:
            task_id = await self.db.add_task(
                user_id, description, days, times, interval_minutes, is_one_time, one_time_date
            )
            
            task = await self.db.get_task(task_id)
            if task:
                self.reminder_manager.schedule_task(task)
            
            await update.message.reply_text(
                "✅ Нагадування успішно створено!",
                reply_markup=MAIN_MARKUP
            )
            await self._send_task_message(update, task)
        
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            await update.message.reply_text(
                "❌ Помилка створення нагадування. Спробуй ще раз.",
                reply_markup=MAIN_MARKUP
            )
        
        finally:
            # Cleanup
            context.user_data.clear()
            if user_id in self.reminder_manager.user_day_selections:
                del self.reminder_manager.user_day_selections[user_id]
        
        return ConversationHandler.END

    # ==================== VIEW REMINDERS ====================
    
    async def view_reminders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View all user reminders using interactive dashboard pagination"""
        if not update.message or not update.effective_user:
            return
        
        user_id = update.effective_user.id
        tasks = await self.db.get_user_tasks(user_id)
        
        if not tasks:
            await update.message.reply_text(
                "📭 *У тебе ще немає нагадувань\\.*\n"
                "Натисни '➕ Створити нагадування', щоб додати\\!",
                parse_mode='MarkdownV2',
                reply_markup=MAIN_MARKUP
            )
            return
        
        # Show first task in interactive dashboard
        first_task = tasks[0]
        card_text = format_task_card(first_task, title=f"📋 *Панель нагадувань* \\(1/{len(tasks)}\\)")
        markup = build_dashboard_keyboard(first_task['task_id'], 0, len(tasks))
        
        await update.message.reply_text(
            card_text,
            parse_mode='MarkdownV2',
            reply_markup=markup
        )

    # ==================== SNOOZE ALL ====================

    async def snooze_all_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ask user for how long to snooze all reminders."""
        if not update.message or not update.effective_user:
            return

        context.user_data['snooze_all_pending'] = True

        keyboard = [
            ['30 хвилин', '1 година'],
            ['Власний інтервал'],
            ['🏠 Скасувати'],
        ]

        await update.message.reply_text(
            "⏸ *На скільки часу відкласти всі нагадування\\?*",
            parse_mode='MarkdownV2',
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        )

    async def _send_task_message(self, update: Update, task: dict):
        """Send formatted task message"""
        card_text = format_task_card(task)
        markup = build_dashboard_keyboard(task['task_id'], 0, 1)
        
        if update.message:
            await update.message.reply_text(
                card_text,
                parse_mode='MarkdownV2',
                reply_markup=markup
            )

    # ==================== DELETE REMINDERS ====================
    
    async def delete_reminder_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start reminder deletion"""
        if not update.message or not update.effective_user:
            return
        
        user_id = update.effective_user.id
        tasks = await self.db.get_user_tasks(user_id)
        
        if not tasks:
            await update.message.reply_text(
                "📭 У тебе немає нагадувань для видалення.",
                reply_markup=MAIN_MARKUP
            )
            return
        
        for task in tasks:
            keyboard = [[InlineKeyboardButton("🗑 Видалити", callback_data=f"delete_{task['task_id']}", api_kwargs={'style': 'danger'})]]
            
            one_time_date = task.get('one_time_date')
            if one_time_date:
                try:
                    if len(one_time_date) > 10:
                        date_dt = datetime.strptime(one_time_date, '%Y-%m-%d %H:%M')
                        days_str = f"Дата: {date_dt.strftime('%d.%m.%Y %H:%M')}"
                    else:
                        date_dt = datetime.strptime(one_time_date, '%Y-%m-%d')
                        days_str = f"Дата: {date_dt.strftime('%d.%m.%Y')}"
                except ValueError:
                    days_str = f"Дата: {one_time_date}"
            else:
                days_str = ', '.join([DayOfWeek.from_index(d).full for d in task['days']]) if task['days'] else 'Не вказано'
            
            await update.message.reply_text(
                f"📝 *Завдання:* {task['description']}\n"
                f"📅 *{'Дата' if one_time_date else 'Дні'}:* {days_str}\n"
                f"⏰ *Часи:* {', '.join(task['times'])}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        await update.message.reply_text(
            "👆 Обери, яке нагадування видалити.",
            reply_markup=MAIN_MARKUP
        )

    # ==================== BUTTON HANDLERS ====================
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button presses"""
        query = update.callback_query
        if not query or not query.data:
            return
        
        data = query.data
        
        try:
            if data == 'noop':
                await query.answer()
            elif data.startswith('page_'):
                await self._handle_page(query, data)
            elif data.startswith('delete_'):
                await self._handle_delete(query, data)
            elif data.startswith('done_'):
                await self._handle_done(query, data)
            elif data.startswith('snooze_'):
                await self._handle_snooze_single(query, data, context)
            elif data.startswith('snoozeopt_'):
                await self._handle_snooze_option(query, data, context)
            elif data.startswith('edit_'):
                pass
        except Exception as e:
            logger.error(f"Error handling button: {e}")
            await query.answer("❌ Виникла помилка. Спробуй ще раз.", show_alert=True)

    async def _handle_page(self, query, data: str):
        """Handle dashboard pagination"""
        try:
            target_idx = int(data.split('_')[1])
        except (IndexError, ValueError):
            await query.answer()
            return
            
        user_id = query.from_user.id
        tasks = await self.db.get_user_tasks(user_id)
        
        if not tasks:
            await query.edit_message_text(
                "📭 *У тебе більше немає активних нагадувань\\.*",
                parse_mode='MarkdownV2'
            )
            return
            
        target_idx = target_idx % len(tasks)
        task = tasks[target_idx]
        card_text = format_task_card(task, title=f"📋 *Панель нагадувань* \\({target_idx + 1}/{len(tasks)}\\)")
        markup = build_dashboard_keyboard(task['task_id'], target_idx, len(tasks))
        
        try:
            await query.edit_message_text(
                card_text,
                parse_mode='MarkdownV2',
                reply_markup=markup
            )
        except Exception:
            pass
        await query.answer()


    async def _handle_delete(self, query, data: str):
        """Handle task deletion"""
        try:
            task_id = int(data.split('_')[1])
        except (IndexError, ValueError):
            await query.edit_message_text("❌ Неправильний формат даних.")
            return
        
        task = await self.db.get_task(task_id)
        if not task:
            await query.edit_message_text("❌ Завдання не знайдено.")
            return
        
        # Cancel scheduled jobs
        self.reminder_manager.cancel_task(task['user_id'], task_id)
        
        # Delete from database
        await self.db.delete_task(task_id)
        
        await query.edit_message_text(f"🗑 Завдання '{task['description']}' було видалено.")

    async def _handle_done(self, query, data: str):
        """Handle task completion"""
        try:
            parts = data.split('_')
            task_id = int(parts[1])
            time_part = '_'.join(parts[2:])
        except (IndexError, ValueError):
            await query.edit_message_text("❌ Неправильний формат даних.")
            return
        
        if not query.from_user:
            return
        
        user_id = query.from_user.id
        task = await self.db.get_task(task_id)
        
        if not task:
            await query.edit_message_text("❌ Завдання не знайдено.")
            return
        
        reminder_instance_id = f"{task_id}_{time_part}"
        
        # Cancel any active repeat tasks for this reminder instance
        self.reminder_manager._cancel_repeat_tasks(reminder_instance_id)
        
        # Mark as completed
        await self.db.mark_reminder_completed(user_id, task_id, reminder_instance_id)
        
        # Format time for display
        if len(time_part) == 4:
            time_display = f"{time_part[:2]}:{time_part[2:]}"
        else:
            time_display = time_part
        
        is_one_time = task.get('is_one_time', False)
        
        if is_one_time:
            # Delete one-time task
            self.reminder_manager.cancel_task(user_id, task_id)
            await self.db.delete_task(task_id)
            
            await query.edit_message_text(
                f"✅ Нагадування '{task['description']}' о {time_display} виконано!\n\n"
                f"Одноразове завдання було автоматично видалено."
            )
        else:
            await query.edit_message_text(
                f"✅ Нагадування '{task['description']}' о {time_display} позначено як виконане!"
            )

    # ==================== SNOOZE HANDLERS ====================

    async def _handle_snooze_single(self, query, data: str, context: ContextTypes.DEFAULT_TYPE):
        """Start snooze flow for a single reminder instance."""
        try:
            parts = data.split('_')
            task_id = int(parts[1])
            time_part = '_'.join(parts[2:])
        except (IndexError, ValueError):
            await query.answer("❌ Неправильний формат даних.", show_alert=True)
            return

        keyboard = [
            [
                InlineKeyboardButton(
                    "30 хвилин",
                    callback_data=f"snoozeopt_{task_id}_{time_part}_30",
                ),
                InlineKeyboardButton(
                    "1 година",
                    callback_data=f"snoozeopt_{task_id}_{time_part}_60",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏱️ Власний інтервал",
                    callback_data=f"snoozeopt_{task_id}_{time_part}_custom",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Скасувати",
                    callback_data=f"snoozeopt_{task_id}_{time_part}_cancel",
                )
            ],
        ]

        await query.answer()
        await query.message.reply_text(
            "⏸ На скільки відкласти це нагадування?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _handle_snooze_option(self, query, data: str, context: ContextTypes.DEFAULT_TYPE):
        """Handle choice of snooze duration for a single reminder."""
        try:
            parts = data.split('_')
            task_id = int(parts[1])
            time_part = parts[2]
            option = parts[3]
        except (IndexError, ValueError):
            await query.answer("❌ Неправильний формат даних.", show_alert=True)
            return

        if option == 'cancel':
            await query.answer("Відкладення скасовано.")
            await query.message.delete()
            return

        if option == 'custom':
            # Ask user for custom interval in minutes via normal message
            context.user_data['snooze_custom_single'] = {
                'task_id': task_id,
                'time_part': time_part,
            }
            await query.answer()
            await query.message.reply_text(
                "⏱️ Введи інтервал (у хвилинах, наприклад 90, або години:хвилини, наприклад 1:30), на який відкласти це нагадування:",
                reply_markup=CANCEL_MARKUP
            )
            return

        # Fixed option in minutes
        try:
            minutes = int(option)
        except ValueError:
            await query.answer("❌ Невідомий інтервал.", show_alert=True)
            return

        if not query.from_user:
            return

        user_id = query.from_user.id
        await self._apply_snooze_single(user_id, task_id, time_part, minutes)
        await query.answer()
        await query.message.edit_text(
            f"⏸ Нагадування відкладено на {minutes} хвилин."
        )

    async def _apply_snooze_single(
        self,
        user_id: int,
        task_id: int,
        time_part: str,
        minutes: int,
    ) -> None:
        """Persist snooze for a single reminder instance."""
        task = await self.db.get_task(task_id)
        if not task:
            return

        reminder_instance_id = f"{task_id}_{time_part}"
        now = datetime.now(TZ)
        snoozed_until = now + timedelta(minutes=minutes)

        await self.db.set_reminder_snooze(
            user_id=user_id,
            task_id=task_id,
            reminder_instance_id=reminder_instance_id,
            snoozed_until=snoozed_until,
        )

    async def handle_snooze_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text input for custom snooze intervals and 'snooze all' flow."""
        if not update.message or not update.message.text or not update.effective_user:
            return

        text = update.message.text.strip()
        user_id = update.effective_user.id

        # Custom single reminder snooze
        if 'snooze_custom_single' in context.user_data:
            data = context.user_data.pop('snooze_custom_single', None)
            if not data:
                return

            if text == '🏠 Скасувати':
                await update.message.reply_text(
                    "⏸ Відкладення скасовано.",
                    reply_markup=MAIN_MARKUP,
                )
                return

            minutes = self.validator.parse_interval(text)
            if minutes is None:
                await update.message.reply_text(
                    "⚠️ Будь ласка, введи інтервал (у хвилинах або години:хвилини) або '🏠 Скасувати'.",
                )
                # Keep state so user can try again
                context.user_data['snooze_custom_single'] = data
                return

            if not self.validator.validate_interval(minutes):
                await update.message.reply_text(
                    "⚠️ Інтервал має бути від 1 до 1440 хвилин. Спробуй ще раз:",
                )
                context.user_data['snooze_custom_single'] = data
                return

            await self._apply_snooze_single(
                user_id=user_id,
                task_id=data['task_id'],
                time_part=data['time_part'],
                minutes=minutes,
            )
            await update.message.reply_text(
                f"⏸ Нагадування відкладено на {minutes} хвилин.",
                reply_markup=MAIN_MARKUP,
            )
            return

        # Snooze all reminders flow
        if context.user_data.get('snooze_all_pending'):
            if text == '🏠 Скасувати':
                context.user_data.pop('snooze_all_pending', None)
                await update.message.reply_text(
                    "⏸ Відкладення всіх нагадувань скасовано.",
                    reply_markup=MAIN_MARKUP,
                )
                return

            interval_map = {
                '30 хвилин': 30,
                '1 година': 60,
            }

            minutes = interval_map.get(text)
            if minutes is None:
                if text == 'Власний інтервал':
                    await update.message.reply_text(
                        "⏱️ Введи інтервал (у хвилинах, наприклад 90, або години:хвилини, наприклад 1:30):",
                    )
                    return

                # Treat as custom minutes
                minutes = self.validator.parse_interval(text)
                if minutes is None:
                    await update.message.reply_text(
                        "⚠️ Введи інтервал (у хвилинах або години:хвилини) або обери варіант з клавіатури.",
                    )
                    return

            if not self.validator.validate_interval(minutes):
                await update.message.reply_text(
                    "⚠️ Інтервал має бути від 1 до 1440 хвилин. Спробуй ще раз:",
                )
                return

            now = datetime.now(TZ)
            snoozed_until = now + timedelta(minutes=minutes)
            await self.db.set_user_snooze(user_id, snoozed_until)

            context.user_data.pop('snooze_all_pending', None)

            await update.message.reply_text(
                f"⏸ Усі нагадування відкладено на {minutes} хвилин.",
                reply_markup=MAIN_MARKUP,
            )
