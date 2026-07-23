import logging
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from core.config import TIMEZONE
from core.scheduler import DayOfWeek
from .states import ConversationState
from .keyboards import MAIN_MARKUP
from .ui_helpers import (
    escape_md, format_edit_menu_card, format_edit_field_card,
    build_edit_menu_keyboard, build_edit_interval_keyboard,
    build_edit_times_keyboard, build_edit_desc_keyboard,
    build_edit_days_keyboard, format_one_time_date_display
)

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)

class EditHandlers:
    """Handlers for editing reminders with unified Rich MarkdownV2 UI."""
    
    def __init__(self, db, reminder_manager, validator):
        self.db = db
        self.reminder_manager = reminder_manager
        self.validator = validator

    async def edit_reminder_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start edit flow from callback."""
        query = update.callback_query
        await query.answer()
        
        try:
            task_id = int(query.data.split('_')[1])
        except (IndexError, ValueError):
            await query.edit_message_text("❌ Неправильний формат даних.")
            return ConversationHandler.END
            
        task = await self.db.get_task(task_id)
        if not task:
            await query.edit_message_text("❌ Завдання не знайдено.")
            return ConversationHandler.END
            
        context.user_data.clear()
        context.user_data['edit_task_id'] = task_id
        context.user_data['edit_task'] = task
        context.user_data['edit_message_id'] = query.message.message_id
        context.user_data['edit_temp'] = {
            'days': list(task.get('days', [])),
            'is_one_time': task.get('is_one_time', False),
            'everyday': (len(task.get('days', [])) == 7 and not task.get('is_one_time')),
            'one_time_date': task.get('one_time_date')
        }
        
        await query.edit_message_text(
            text=format_edit_menu_card(task),
            reply_markup=build_edit_menu_keyboard(task_id),
            parse_mode='MarkdownV2'
        )
        return ConversationState.EDIT_SELECT_FIELD.value

    async def edit_select_field(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle field selection from main edit menu."""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == 'edit_cancel':
            await query.edit_message_text("✏️ *Редагування скасовано\\.*", parse_mode='MarkdownV2')
            context.user_data.clear()
            return ConversationHandler.END

        if data == 'edit_back_main':
            task_id = context.user_data.get('edit_task_id')
            task = await self.db.get_task(task_id)
            if not task:
                await query.edit_message_text("❌ Завдання не знайдено.")
                context.user_data.clear()
                return ConversationHandler.END
            context.user_data['edit_task'] = task
            await query.edit_message_text(
                text=format_edit_menu_card(task),
                reply_markup=build_edit_menu_keyboard(task_id),
                parse_mode='MarkdownV2'
            )
            return ConversationState.EDIT_SELECT_FIELD.value
            
        field_map = {
            'edit_field_description': 'description',
            'edit_field_type': 'type',
            'edit_field_times': 'times',
            'edit_field_interval': 'interval'
        }
        
        field = field_map.get(data)
        if not field:
            return ConversationState.EDIT_SELECT_FIELD.value
            
        context.user_data['edit_field'] = field
        task_id = context.user_data.get('edit_task_id')
        task = context.user_data.get('edit_task', {})
        
        if field == 'description':
            await query.edit_message_text(
                text=format_edit_field_card(task, 'description'),
                reply_markup=build_edit_desc_keyboard(),
                parse_mode='MarkdownV2'
            )
            return ConversationState.EDIT_ENTER_VALUE.value
            
        elif field == 'times':
            await query.edit_message_text(
                text=format_edit_field_card(task, 'times'),
                reply_markup=build_edit_times_keyboard(task_id, task.get('times', [])),
                parse_mode='MarkdownV2'
            )
            return ConversationState.EDIT_ENTER_VALUE.value
            
        elif field == 'interval':
            await query.edit_message_text(
                text=format_edit_field_card(task, 'interval'),
                reply_markup=build_edit_interval_keyboard(task_id, task.get('interval_minutes', 0)),
                parse_mode='MarkdownV2'
            )
            return ConversationState.EDIT_ENTER_VALUE.value
            
        elif field == 'type':
            temp = context.user_data.setdefault('edit_temp', {
                'days': list(task.get('days', [])),
                'is_one_time': task.get('is_one_time', False),
                'everyday': (len(task.get('days', [])) == 7 and not task.get('is_one_time')),
                'one_time_date': task.get('one_time_date')
            })
            markup = build_edit_days_keyboard(
                temp['days'],
                is_one_time=temp['is_one_time'],
                everyday=temp['everyday'],
                one_time_date=temp['one_time_date']
            )
            await query.edit_message_text(
                text=format_edit_field_card(task, 'type', temp),
                reply_markup=markup,
                parse_mode='MarkdownV2'
            )
            return ConversationState.EDIT_CHOOSING_DAYS.value

    async def edit_callback_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callback queries during edit submenus."""
        query = update.callback_query
        if not query or not query.data:
            return ConversationState.EDIT_ENTER_VALUE.value
        
        await query.answer()
        data = query.data
        
        if data == 'edit_cancel':
            await query.edit_message_text("✏️ *Редагування скасовано\\.*", parse_mode='MarkdownV2')
            context.user_data.clear()
            return ConversationHandler.END

        if data == 'edit_back_main':
            task_id = context.user_data.get('edit_task_id')
            task = await self.db.get_task(task_id)
            if not task:
                await query.edit_message_text("❌ Завдання не знайдено.")
                context.user_data.clear()
                return ConversationHandler.END
            context.user_data['edit_task'] = task
            await query.edit_message_text(
                text=format_edit_menu_card(task),
                reply_markup=build_edit_menu_keyboard(task_id),
                parse_mode='MarkdownV2'
            )
            return ConversationState.EDIT_SELECT_FIELD.value

        task_id = context.user_data.get('edit_task_id')
        task = context.user_data.get('edit_task', {})
        if not task_id or not task:
            await query.edit_message_text("❌ Завдання не знайдено.")
            context.user_data.clear()
            return ConversationHandler.END

        # Interactive day selection (editday_*)
        if data.startswith('editday_'):
            action = data.split('_')[1]
            temp = context.user_data.setdefault('edit_temp', {
                'days': list(task.get('days', [])),
                'is_one_time': task.get('is_one_time', False),
                'everyday': (len(task.get('days', [])) == 7 and not task.get('is_one_time')),
                'one_time_date': task.get('one_time_date')
            })
            
            if action == 'everyday':
                temp['days'] = list(range(7))
                temp['everyday'] = True
                temp['is_one_time'] = False
                temp['one_time_date'] = None
            elif action == 'onetime':
                temp['days'] = []
                temp['everyday'] = False
                temp['is_one_time'] = True
                temp['one_time_date'] = None
            else:
                try:
                    idx = int(action)
                    if idx in temp['days']:
                        temp['days'].remove(idx)
                    else:
                        temp['days'].append(idx)
                    temp['days'].sort()
                    temp['is_one_time'] = False
                    temp['one_time_date'] = None
                    temp['everyday'] = (len(temp['days']) == 7)
                except ValueError:
                    pass
                    
            markup = build_edit_days_keyboard(
                temp['days'],
                is_one_time=temp['is_one_time'],
                everyday=temp['everyday'],
                one_time_date=temp['one_time_date']
            )
            try:
                await query.edit_message_text(
                    text=format_edit_field_card(task, 'type', temp),
                    reply_markup=markup,
                    parse_mode='MarkdownV2'
                )
            except Exception:
                pass
            return ConversationState.EDIT_CHOOSING_DAYS.value

        if data == 'edit_days_confirm':
            temp = context.user_data.get('edit_temp', {})
            days = temp.get('days', [])
            is_one_time = temp.get('is_one_time', False)
            one_time_date = temp.get('one_time_date')
            
            if not days and not is_one_time and not one_time_date:
                await query.answer("⚠️ Обери хоча б один день або вкажи дату!", show_alert=True)
                return ConversationState.EDIT_CHOOSING_DAYS.value
                
            await self.db.update_task(task_id, days=days, is_one_time=is_one_time, one_time_date=one_time_date)
            updated_task = await self.db.get_task(task_id)
            self.reminder_manager.cancel_task(updated_task['user_id'], task_id)
            self.reminder_manager.schedule_task(updated_task)
            
            await query.edit_message_text("✅ *Розклад нагадування успішно оновлено\\!*", parse_mode='MarkdownV2')
            context.user_data.clear()
            return ConversationHandler.END

        updates = {}
        if data.startswith('editint_'):
            try:
                val = int(data.split('_')[2])
                updates['interval_minutes'] = val
            except (IndexError, ValueError):
                await query.answer("❌ Помилка даних", show_alert=True)
                return ConversationState.EDIT_ENTER_VALUE.value

        elif data.startswith('edittime_'):
            time_val = data.split('_')[2]
            updates['times'] = [time_val]

        if updates:
            await self.db.update_task(task_id, **updates)
            updated_task = await self.db.get_task(task_id)
            self.reminder_manager.cancel_task(updated_task['user_id'], task_id)
            self.reminder_manager.schedule_task(updated_task)

            await query.edit_message_text("✅ *Завдання успішно оновлено\\!*", parse_mode='MarkdownV2')
            context.user_data.clear()
            return ConversationHandler.END

        return ConversationState.EDIT_ENTER_VALUE.value

    async def edit_enter_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle new value input via text chat message."""
        if not update.message or not update.message.text:
            return ConversationHandler.END
            
        text = update.message.text.strip()
        
        try:
            await update.message.delete()
        except Exception:
            pass
            
        edit_msg_id = context.user_data.get('edit_message_id')
        if text in ('🏠 Скасувати', '❌ Скасувати', 'Скасувати', '/cancel'):
            if edit_msg_id and update.effective_chat:
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=edit_msg_id,
                        text="✏️ *Редагування скасовано\\.*",
                        parse_mode='MarkdownV2'
                    )
                except Exception:
                    pass
            else:
                await update.message.reply_text("✏️ *Редагування скасовано\\.*", parse_mode='MarkdownV2', reply_markup=MAIN_MARKUP)
            context.user_data.clear()
            return ConversationHandler.END
            
        field = context.user_data.get('edit_field')
        task_id = context.user_data.get('edit_task_id')
        task = context.user_data.get('edit_task', {})
        
        updates = {}
        
        if field == 'description':
            updates['description'] = text
            
        elif field == 'times':
            valid_times, invalid_times = self.validator.parse_times(text)
            if invalid_times or not valid_times:
                if edit_msg_id and update.effective_chat:
                    try:
                        err_msg = f"⚠️ *Неправильний формат часу:* `{escape_md(', '.join(invalid_times or [text]))}`\\.\nСпробуй ще раз:"
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=edit_msg_id,
                            text=f"{format_edit_field_card(task, 'times')}\n\n{err_msg}",
                            reply_markup=build_edit_times_keyboard(task_id, task.get('times', [])),
                            parse_mode='MarkdownV2'
                        )
                    except Exception:
                        pass
                return ConversationState.EDIT_ENTER_VALUE.value
            updates['times'] = valid_times
            
        elif field == 'interval':
            if text.lower() in ('не повторювати', '0', 'без повторів'):
                val = 0
            else:
                val = self.validator.parse_interval(text)
                if val is None or not self.validator.validate_interval(val):
                    if edit_msg_id and update.effective_chat:
                        try:
                            err_msg = "⚠️ *Неправильний інтервал\\. Введи хвилини \\(1-1440\\) або години:хвилини \\(наприклад: 45 чи 1:30\\)*"
                            await context.bot.edit_message_text(
                                chat_id=update.effective_chat.id,
                                message_id=edit_msg_id,
                                text=f"{format_edit_field_card(task, 'interval')}\n\n{err_msg}",
                                reply_markup=build_edit_interval_keyboard(task_id, task.get('interval_minutes', 0)),
                                parse_mode='MarkdownV2'
                            )
                        except Exception:
                            pass
                    return ConversationState.EDIT_ENTER_VALUE.value
            updates['interval_minutes'] = val
            
        elif field == 'type':
            date_str, _ = self.validator.parse_date(text)
            if date_str:
                updates['one_time_date'] = date_str
                updates['is_one_time'] = True
                updates['days'] = []
            else:
                if edit_msg_id and update.effective_chat:
                    try:
                        temp = context.user_data.get('edit_temp', {})
                        err_msg = f"⚠️ *Не вдалося розпізнати дату:* `{escape_md(text)}`\\.\nСпробуй ще раз:"
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=edit_msg_id,
                            text=f"{format_edit_field_card(task, 'type', temp)}\n\n{err_msg}",
                            reply_markup=build_edit_days_keyboard(temp.get('days', []), is_one_time=temp.get('is_one_time'), everyday=temp.get('everyday'), one_time_date=temp.get('one_time_date')),
                            parse_mode='MarkdownV2'
                        )
                    except Exception:
                        pass
                return ConversationState.EDIT_CHOOSING_DAYS.value

        # Apply updates
        if updates:
            await self.db.update_task(task_id, **updates)
            updated_task = await self.db.get_task(task_id)
            self.reminder_manager.cancel_task(updated_task['user_id'], task_id)
            self.reminder_manager.schedule_task(updated_task)
            
            if edit_msg_id and update.effective_chat:
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=edit_msg_id,
                        text="✅ *Завдання успішно оновлено\\!*",
                        parse_mode='MarkdownV2'
                    )
                except Exception:
                    pass
            context.user_data.clear()
            return ConversationHandler.END
            
        return ConversationState.EDIT_ENTER_VALUE.value

    async def edit_choosing_days(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Delegate text input in EDIT_CHOOSING_DAYS phase to edit_enter_value."""
        return await self.edit_enter_value(update, context)

    async def edit_choosing_one_time_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Delegate text input in EDIT_CHOOSING_ONE_TIME_DATE phase to edit_enter_value."""
        return await self.edit_enter_value(update, context)
