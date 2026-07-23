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
    format_reminder_notification, get_task_type_str,
    format_wizard_step, build_wiz_days_keyboard,
    build_wiz_times_keyboard, build_wiz_interval_keyboard,
    format_snooze_card, build_snooze_keyboard,
    format_snooze_all_card, build_snooze_all_keyboard
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

    # ==================== CREATE REMINDER FLOW (SINGLE-MESSAGE WIZARD) ====================
    
    async def create_reminder_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start Single-Message Wizard for reminder creation"""
        if not update.message:
            return
        
        context.user_data.clear()
        context.user_data['wizard_data'] = {'days': [], 'times': [], 'interval_minutes': 0}
        
        cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Скасувати", callback_data="wiz_cancel", api_kwargs={'style': 'danger'})]])
        
        msg = await update.message.reply_text(
            format_wizard_step(1, context.user_data['wizard_data']),
            parse_mode='MarkdownV2',
            reply_markup=cancel_markup
        )
        context.user_data['wizard_message_id'] = msg.message_id
        return ConversationState.DESCRIBING_TASK.value
    
    async def get_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get task description and advance Single-Message Wizard to step 2"""
        if not update.message or not update.message.text:
            return ConversationHandler.END
        
        text = update.message.text.strip()
        
        try:
            await update.message.delete()
        except Exception:
            pass
            
        if text in ('🏠 Скасувати', '/cancel'):
            return await self._cancel_wizard(update, context)
            
        context.user_data['wizard_data']['description'] = text
        
        wiz_msg_id = context.user_data.get('wizard_message_id')
        markup = build_wiz_days_keyboard(context.user_data['wizard_data']['days'])
        
        if wiz_msg_id and update.effective_chat:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=wiz_msg_id,
                    text=format_wizard_step(2, context.user_data['wizard_data']),
                    parse_mode='MarkdownV2',
                    reply_markup=markup
                )
            except Exception as e:
                logger.error(f"Error editing wizard msg: {e}")
        return ConversationState.CHOOSING_DAYS.value

    async def get_days(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle custom date or day text input in step 2 of wizard"""
        if not update.message or not update.message.text:
            return ConversationState.CHOOSING_DAYS.value

        text = update.message.text.strip()
        try:
            await update.message.delete()
        except Exception:
            pass

        if text in ('🏠 Скасувати', '/cancel'):
            return await self._cancel_wizard(update, context)

        wiz_data = context.user_data.setdefault('wizard_data', {'days': [], 'times': [], 'interval_minutes': 0})
        date_str, time_str = self.validator.parse_date(text)

        wiz_msg_id = context.user_data.get('wizard_message_id')

        if date_str:
            wiz_data['one_time_date'] = date_str
            wiz_data['is_one_time'] = True
            wiz_data['everyday'] = False
            wiz_data['days'] = []

            if time_str and time_str not in wiz_data['times']:
                wiz_data['times'].append(time_str)

            if wiz_data['times']:
                markup = build_wiz_interval_keyboard(wiz_data.get('interval_minutes', 0))
                next_step = 4
                next_state = ConversationState.CHOOSING_INTERVAL.value
            else:
                markup = build_wiz_times_keyboard(wiz_data['times'])
                next_step = 3
                next_state = ConversationState.CHOOSING_TIMES.value

            if wiz_msg_id and update.effective_chat:
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=wiz_msg_id,
                        text=format_wizard_step(next_step, wiz_data),
                        parse_mode='MarkdownV2',
                        reply_markup=markup
                    )
                except Exception as e:
                    logger.error(f"Error editing wizard msg: {e}")

            return next_state

        return ConversationState.CHOOSING_DAYS.value

    async def get_times(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle custom text input for times (e.g., 09:30, 18:00) in wizard"""
        if not update.message or not update.message.text:
            return ConversationState.CHOOSING_TIMES.value
            
        text = update.message.text.strip()
        try:
            await update.message.delete()
        except Exception:
            pass
            
        wiz_data = context.user_data.setdefault('wizard_data', {'days': [], 'times': [], 'interval_minutes': 0})
        valid_times, invalid_times = self.validator.parse_times(text)
        
        wiz_msg_id = context.user_data.get('wizard_message_id')
        
        if invalid_times or not valid_times:
            return ConversationState.CHOOSING_TIMES.value
            
        # Combine custom entered times with existing selected times
        existing = set(wiz_data.get('times', []))
        existing.update(valid_times)
        wiz_data['times'] = sorted(list(existing))
        
        markup = build_wiz_times_keyboard(wiz_data['times'])
        
        if wiz_msg_id and update.effective_chat:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=wiz_msg_id,
                    text=format_wizard_step(3, wiz_data),
                    parse_mode='MarkdownV2',
                    reply_markup=markup
                )
            except Exception as e:
                logger.error(f"Error editing wizard msg: {e}")
        return ConversationState.CHOOSING_TIMES.value

    async def get_interval(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle custom text input for interval (e.g., 45, 90, 1:30) in wizard"""
        if not update.message or not update.message.text:
            return ConversationState.CHOOSING_INTERVAL.value
            
        text = update.message.text.strip()
        try:
            await update.message.delete()
        except Exception:
            pass
            
        wiz_data = context.user_data.setdefault('wizard_data', {'days': [], 'times': [], 'interval_minutes': 0})
        parsed_interval = self.validator.parse_interval(text)
        
        wiz_msg_id = context.user_data.get('wizard_message_id')
        
        if parsed_interval is None or not self.validator.validate_interval(parsed_interval):
            return ConversationState.CHOOSING_INTERVAL.value
            
        wiz_data['interval_minutes'] = parsed_interval
        markup = build_wiz_interval_keyboard(parsed_interval)
        
        if wiz_msg_id and update.effective_chat:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=wiz_msg_id,
                    text=format_wizard_step(4, wiz_data),
                    parse_mode='MarkdownV2',
                    reply_markup=markup
                )
            except Exception as e:
                logger.error(f"Error editing wizard msg: {e}")
        return ConversationState.CHOOSING_INTERVAL.value

    async def _cancel_wizard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel wizard helper"""
        wiz_msg_id = context.user_data.get('wizard_message_id')
        if wiz_msg_id and update.effective_chat:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=wiz_msg_id,
                    text="❌ *Створення нагадування скасовано\\.*",
                    parse_mode='MarkdownV2'
                )
            except Exception:
                pass
        context.user_data.clear()
        return ConversationHandler.END

    async def handle_wizard_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button clicks inside the Single-Message Wizard"""
        query = update.callback_query
        if not query or not query.data:
            return
        
        data = query.data
        wiz_data = context.user_data.get('wizard_data', {'days': [], 'times': [], 'interval_minutes': 0})
        
        if data == 'wiz_cancel':
            await query.answer("Створення скасовано.")
            await query.edit_message_text("❌ *Створення нагадування скасовано\\.*", parse_mode='MarkdownV2')
            context.user_data.clear()
            return ConversationHandler.END

        if data.startswith('wizback_'):
            step_to = int(data.split('_')[1])
            await query.answer()
            if step_to == 1:
                cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Скасувати", callback_data="wiz_cancel", api_kwargs={'style': 'danger'})]])
                await query.edit_message_text(
                    format_wizard_step(1, wiz_data),
                    parse_mode='MarkdownV2',
                    reply_markup=cancel_markup
                )
                return ConversationState.DESCRIBING_TASK.value
            elif step_to == 2:
                markup = build_wiz_days_keyboard(
                    wiz_data['days'],
                    wiz_data.get('is_one_time', False),
                    wiz_data.get('everyday', False),
                    wiz_data.get('one_time_date')
                )
                await query.edit_message_text(
                    format_wizard_step(2, wiz_data),
                    parse_mode='MarkdownV2',
                    reply_markup=markup
                )
                return ConversationState.CHOOSING_DAYS.value
            elif step_to == 3:
                markup = build_wiz_times_keyboard(wiz_data['times'])
                await query.edit_message_text(
                    format_wizard_step(3, wiz_data),
                    parse_mode='MarkdownV2',
                    reply_markup=markup
                )
                return ConversationState.CHOOSING_TIMES.value
            
        # STEP 2: DAYS & TYPE & DATE
        if data.startswith('wizday_'):
            action = data.split('_')[1]
            if action.isdigit():
                day_idx = int(action)
                if day_idx in wiz_data['days']:
                    wiz_data['days'].remove(day_idx)
                else:
                    wiz_data['days'].append(day_idx)
                wiz_data['is_one_time'] = False
                wiz_data['everyday'] = False
                wiz_data['one_time_date'] = None
            elif action == 'everyday':
                wiz_data['everyday'] = not wiz_data.get('everyday', False)
                if wiz_data['everyday']:
                    wiz_data['days'] = list(range(7))
                    wiz_data['is_one_time'] = False
                    wiz_data['one_time_date'] = None
                else:
                    wiz_data['days'] = []
            elif action == 'onetime':
                wiz_data['is_one_time'] = not wiz_data.get('is_one_time', False)
                wiz_data['everyday'] = False
                wiz_data['days'] = []
                wiz_data['one_time_date'] = None
            elif action == 'confirm':
                if not wiz_data.get('days') and not wiz_data.get('is_one_time') and not wiz_data.get('everyday') and not wiz_data.get('one_time_date'):
                    await query.answer("⚠️ Обери хоча б один день, дату або тип нагадування!", show_alert=True)
                    return ConversationState.CHOOSING_DAYS.value
                await query.answer()
                markup = build_wiz_times_keyboard(wiz_data['times'])
                await query.edit_message_text(
                    format_wizard_step(3, wiz_data),
                    parse_mode='MarkdownV2',
                    reply_markup=markup
                )
                return ConversationState.CHOOSING_TIMES.value
                
            await query.answer()
            markup = build_wiz_days_keyboard(
                wiz_data['days'],
                wiz_data.get('is_one_time', False),
                wiz_data.get('everyday', False),
                wiz_data.get('one_time_date')
            )
            await query.edit_message_text(
                format_wizard_step(2, wiz_data),
                parse_mode='MarkdownV2',
                reply_markup=markup
            )
            return ConversationState.CHOOSING_DAYS.value

        # STEP 3: TIMES
        elif data.startswith('wiztime_'):
            action = data.split('_')[1]
            if action == 'confirm':
                if not wiz_data.get('times'):
                    await query.answer("⚠️ Обери або введи у чат хоча б один час!", show_alert=True)
                    return ConversationState.CHOOSING_TIMES.value
                await query.answer()
                markup = build_wiz_interval_keyboard(wiz_data.get('interval_minutes', 0))
                await query.edit_message_text(
                    format_wizard_step(4, wiz_data),
                    parse_mode='MarkdownV2',
                    reply_markup=markup
                )
                return ConversationState.CHOOSING_INTERVAL.value
            else:
                time_str = action
                if time_str in wiz_data['times']:
                    wiz_data['times'].remove(time_str)
                else:
                    wiz_data['times'].append(time_str)
                wiz_data['times'].sort()
                
                await query.answer()
                markup = build_wiz_times_keyboard(wiz_data['times'])
                await query.edit_message_text(
                    format_wizard_step(3, wiz_data),
                    parse_mode='MarkdownV2',
                    reply_markup=markup
                )
                return ConversationState.CHOOSING_TIMES.value

        # STEP 4: INTERVAL & SAVE
        elif data.startswith('wizint_'):
            interval_val = int(data.split('_')[1])
            wiz_data['interval_minutes'] = interval_val
            await query.answer()
            markup = build_wiz_interval_keyboard(interval_val)
            await query.edit_message_text(
                format_wizard_step(4, wiz_data),
                parse_mode='MarkdownV2',
                reply_markup=markup
            )
            return ConversationState.CHOOSING_INTERVAL.value

        elif data == 'wiz_save':
            await query.answer("🚀 Зберігаємо нагадування...")
            user_id = query.from_user.id
            desc = wiz_data.get('description', 'Без опису')
            days = wiz_data.get('days', [])
            times = wiz_data.get('times', ['09:00'])
            interval = wiz_data.get('interval_minutes', 0)
            is_one_time = wiz_data.get('is_one_time', False)
            one_time_date = wiz_data.get('one_time_date')
            
            task_id = await self.db.add_task(
                user_id, desc, days, times, interval, is_one_time, one_time_date
            )
            task = await self.db.get_task(task_id)
            if task:
                self.reminder_manager.schedule_task(task)
                card_text = format_task_card(task, title="🎉 *Нагадування успішно створено\\!*")
                markup = build_dashboard_keyboard(task_id, 0, 1)
                await query.edit_message_text(
                    card_text,
                    parse_mode='MarkdownV2',
                    reply_markup=markup
                )
            context.user_data.clear()
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
            elif data.startswith('dashdone_'):
                await self._handle_dashdone(query, data, context)
            elif data.startswith('dashsnooze_'):
                await self._handle_dashsnooze(query, data, context)
            elif data.startswith('page_'):
                await self._handle_page(query, data, context)
            elif data.startswith('delete_'):
                await self._handle_delete(query, data)
            elif data.startswith('done_'):
                await self._handle_done(query, data)
            elif data.startswith('snooze_'):
                await self._handle_snooze_single(query, data, context)
            elif data.startswith('snoozeopt_'):
                await self._handle_snooze_option(query, data, context)
            elif data.startswith('snoozeall_'):
                await self._handle_snooze_all_option(query, data, context)
            elif data.startswith('edit_'):
                pass
        except Exception as e:
            logger.error(f"Error handling button: {e}")
            await query.answer("❌ Виникла помилка. Спробуй ще раз.", show_alert=True)

    async def _handle_page(self, query, data: str, context: ContextTypes.DEFAULT_TYPE = None):
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
        if context is not None:
            context.user_data['dashboard_page'] = target_idx
            
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

    async def _handle_dashdone(self, query, data: str, context: ContextTypes.DEFAULT_TYPE):
        """Handle 'Done' button directly from Dashboard card."""
        try:
            task_id = int(data.split('_')[1])
        except (IndexError, ValueError):
            await query.answer("❌ Помилка даних", show_alert=True)
            return

        user_id = query.from_user.id
        next_info = await self.reminder_manager.get_next_reminder_instance(user_id, task_id)
        if not next_info:
            await query.answer("⚠️ Немає активних нагадувань для цієї задачі.", show_alert=True)
            return
            
        rem_inst_id, time_str = next_info
        
        # Stop active repeat tasks for this instance
        self.reminder_manager.cancel_repeat_tasks(rem_inst_id)
        
        task = await self.db.get_task(task_id)
        if not task:
            await query.answer("⚠️ Завдання не знайдено.", show_alert=True)
            return

        await self.db.mark_reminder_completed(user_id, task_id, rem_inst_id)
        
        is_one_time = task.get('is_one_time', False)
        if is_one_time:
            has_remaining = await self.reminder_manager.has_remaining_one_time_slots(user_id, task)
            if not has_remaining:
                self.reminder_manager.cancel_task(user_id, task_id)
                await self.db.delete_task(task_id)
                await query.answer(f"✅ Нагадування о {time_str} виконано! Завдання завершено.", show_alert=True)
            else:
                await query.answer(f"✅ Нагадування о {time_str} виконано!", show_alert=True)
        else:
            await query.answer(f"✅ Нагадування о {time_str} відмічено виконаним!", show_alert=False)

        # Refresh dashboard page
        tasks = await self.db.get_user_tasks(user_id)
        if tasks:
            page = min(context.user_data.get('dashboard_page', 0), len(tasks) - 1)
            await self._handle_page(query, f"page_{page}", context)
        else:
            await query.edit_message_text("📋 *У тебе поки немає активних нагадувань\\!*", parse_mode='MarkdownV2')

    async def _handle_dashsnooze(self, query, data: str, context: ContextTypes.DEFAULT_TYPE):
        """Handle 'Snooze' button directly from Dashboard card."""
        try:
            task_id = int(data.split('_')[1])
        except (IndexError, ValueError):
            await query.answer("❌ Помилка даних", show_alert=True)
            return

        user_id = query.from_user.id
        next_info = await self.reminder_manager.get_next_reminder_instance(user_id, task_id)
        if not next_info:
            await query.answer("⚠️ Немає активних нагадувань для цієї задачі.", show_alert=True)
            return
            
        rem_inst_id, time_str = next_info
        time_part = time_str.replace(':', '')
        fake_data = f"snooze_{task_id}_{time_part}"
        await self._handle_snooze_single(query, fake_data, context)


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
            # Check if there are other future scheduled times for this one-time task
            has_remaining = await self.reminder_manager.has_remaining_one_time_slots(user_id, task)
            if not has_remaining:
                self.reminder_manager.cancel_task(user_id, task_id)
                await self.db.delete_task(task_id)
                await query.edit_message_text(
                    f"✅ *Нагадування '{escape_md(task['description'])}' о {escape_md(time_display)} виконано\\!*\n\n"
                    f"🎉 _Усі нагадування цього завдання завершено, його видалено\\._",
                    parse_mode='MarkdownV2'
                )
            else:
                await query.edit_message_text(
                    f"✅ *Нагадування '{escape_md(task['description'])}' о {escape_md(time_display)} виконано\\!*\n\n"
                    f"⏳ _Залишилися наступні нагадування для цього завдання\\._",
                    parse_mode='MarkdownV2'
                )
        else:
            await query.edit_message_text(
                f"✅ *Нагадування '{escape_md(task['description'])}' о {escape_md(time_display)} позначено як виконане\\!*",
                parse_mode='MarkdownV2'
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

        task = await self.db.get_task(task_id)
        if not task:
            await query.answer("❌ Завдання не знайдено.", show_alert=True)
            return

        time_display = f"{time_part[:2]}:{time_part[2:]}" if len(time_part) == 4 else time_part

        # Store pending custom single snooze state IMMEDIATELY so chat text input works without clicking any "custom" button
        context.user_data['snooze_custom_single'] = {
            'task_id': task_id,
            'time_part': time_part,
            'prompt_msg_id': query.message.message_id if query.message else None
        }

        await query.answer()
        text = format_snooze_card(task, time_display)
        markup = build_snooze_keyboard(task_id, time_part)

        try:
            msg = await query.edit_message_text(text, parse_mode='MarkdownV2', reply_markup=markup)
            if msg:
                context.user_data['snooze_custom_single']['prompt_msg_id'] = msg.message_id
        except Exception:
            msg = await query.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=markup)
            if msg:
                context.user_data['snooze_custom_single']['prompt_msg_id'] = msg.message_id

    async def _handle_snooze_option(self, query, data: str, context: ContextTypes.DEFAULT_TYPE):
        """Handle choice of snooze duration for a single reminder via inline button."""
        try:
            parts = data.split('_')
            task_id = int(parts[1])
            time_part = parts[2]
            option = parts[3]
        except (IndexError, ValueError):
            await query.answer("❌ Неправильний формат даних.", show_alert=True)
            return

        context.user_data.pop('snooze_custom_single', None)

        if option == 'cancel':
            await query.answer("Відкладення скасовано.")
            try:
                await query.edit_message_text("⏸ *Відкладення скасовано\\.*", parse_mode='MarkdownV2')
            except Exception:
                await query.message.delete()
            return

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

        time_str = f"{minutes} хв" if minutes < 60 else f"{minutes // 60} год"
        await query.edit_message_text(
            f"⏸ *Нагадування відкладено на {escape_md(time_str)}\\!*",
            parse_mode='MarkdownV2'
        )

    async def _handle_snooze_all_option(self, query, data: str, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button click for snooze all."""
        try:
            option = data.split('_')[1]
        except (IndexError, ValueError):
            await query.answer("❌ Помилка даних", show_alert=True)
            return

        context.user_data.pop('snooze_all_pending', None)

        if option == 'cancel':
            await query.answer("Скасовано")
            try:
                await query.edit_message_text("⏸ *Відкладення всіх нагадувань скасовано\\.*", parse_mode='MarkdownV2')
            except Exception:
                await query.message.delete()
            return

        try:
            minutes = int(option)
        except ValueError:
            await query.answer("❌ Невідомий інтервал", show_alert=True)
            return

        user_id = query.from_user.id
        now = datetime.now(TZ)
        snoozed_until = now + timedelta(minutes=minutes)
        await self.db.set_user_snooze(user_id, snoozed_until)

        await query.answer()
        time_str = f"{minutes} хв" if minutes < 60 else f"{minutes // 60} год"
        await query.edit_message_text(
            f"⏸ *Усі нагадування відкладено на {escape_md(time_str)}\\!*",
            parse_mode='MarkdownV2'
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
            data = context.user_data.get('snooze_custom_single', {})
            if not data:
                return

            if text in ('🏠 Скасувати', '❌ Скасувати', 'Скасувати', '/cancel'):
                context.user_data.pop('snooze_custom_single', None)
                await update.message.reply_text(
                    "⏸ *Відкладення скасовано\\.*",
                    parse_mode='MarkdownV2',
                    reply_markup=MAIN_MARKUP,
                )
                return

            minutes = self.validator.parse_interval(text)
            if minutes is None or not self.validator.validate_interval(minutes):
                await update.message.reply_text(
                    "⚠️ *Будь ласка, введи інтервал у хвилинах \\(наприклад: 15, 45, 90 чи 1:30\\) або натисни '❌ Скасувати'\\.*",
                    parse_mode='MarkdownV2'
                )
                return

            context.user_data.pop('snooze_custom_single', None)

            await self._apply_snooze_single(
                user_id=user_id,
                task_id=data['task_id'],
                time_part=data['time_part'],
                minutes=minutes,
            )

            prompt_msg_id = data.get('prompt_msg_id')
            if prompt_msg_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=prompt_msg_id,
                        text=f"⏸ *Нагадування відкладено на {minutes} хв\\!*",
                        parse_mode='MarkdownV2'
                    )
                except Exception:
                    pass

            time_str = f"{minutes} хв" if minutes < 60 else f"{minutes // 60} год"
            await update.message.reply_text(
                f"⏸ *Нагадування відкладено на {escape_md(time_str)}\\!*",
                parse_mode='MarkdownV2',
                reply_markup=MAIN_MARKUP,
            )
            return

        # Snooze all reminders flow
        if context.user_data.get('snooze_all_pending'):
            if text in ('🏠 Скасувати', '❌ Скасувати', 'Скасувати', '/cancel'):
                context.user_data.pop('snooze_all_pending', None)
                await update.message.reply_text(
                    "⏸ *Відкладення всех нагадувань скасовано\\.*",
                    parse_mode='MarkdownV2',
                    reply_markup=MAIN_MARKUP,
                )
                return

            minutes = self.validator.parse_interval(text)
            if minutes is None or not self.validator.validate_interval(minutes):
                await update.message.reply_text(
                    "⚠️ *Введи інтервал у хвилинах \\(наприклад: 30, 60 чи 2:00\\) або обери варіант з кнопок\\.*",
                    parse_mode='MarkdownV2'
                )
                return

            now = datetime.now(TZ)
            snoozed_until = now + timedelta(minutes=minutes)
            await self.db.set_user_snooze(user_id, snoozed_until)
            context.user_data.pop('snooze_all_pending', None)

            time_str = f"{minutes} хв" if minutes < 60 else f"{minutes // 60} год"
            await update.message.reply_text(
                f"⏸ *Усі нагадування відкладено на {escape_md(time_str)}\\!*",
                parse_mode='MarkdownV2',
                reply_markup=MAIN_MARKUP,
            )
