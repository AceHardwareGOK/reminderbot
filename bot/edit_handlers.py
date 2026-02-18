import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

from core.scheduler import DayOfWeek
from .states import ConversationState
from .keyboards import CANCEL_MARKUP, MAIN_MARKUP

from zoneinfo import ZoneInfo
from core.config import TIMEZONE

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)

class EditHandlers:
    """Handlers for editing reminders"""
    
    def __init__(self, db, reminder_manager, validator):
        self.db = db
        self.reminder_manager = reminder_manager
        self.validator = validator

    async def edit_reminder_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start edit flow from callback"""
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
            
        context.user_data['edit_task_id'] = task_id
        context.user_data['edit_task'] = task
        
        keyboard = [
            [InlineKeyboardButton("📝 Опис", callback_data='edit_field_description')],
            [InlineKeyboardButton("📅 Одноразове/Повторюване", callback_data='edit_field_type')],
            [InlineKeyboardButton("⏰ Час", callback_data='edit_field_times')],
            [InlineKeyboardButton("⏱️ Інтервал", callback_data='edit_field_interval')],
            [InlineKeyboardButton("🔙 Скасувати", callback_data='edit_cancel')]
        ]
        
        await query.edit_message_text(
            f"✏️ Що ти хочеш змінити у завданні:\n*{task['description']}*?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return ConversationState.EDIT_SELECT_FIELD.value

    async def edit_select_field(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle field selection"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == 'edit_cancel':
            await query.edit_message_text("✏️ Редагування скасовано.")
            context.user_data.clear()
            return ConversationHandler.END
            
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
        
        if field == 'description':
            await query.message.reply_text(
                "📝 Введи новий опис завдання:",
                reply_markup=CANCEL_MARKUP
            )
            return ConversationState.EDIT_ENTER_VALUE.value
            
        elif field == 'times':
            await query.message.reply_text(
                "⏰ Введи нові часи (через кому, наприклад 09:00, 18:00):",
                reply_markup=CANCEL_MARKUP
            )
            return ConversationState.EDIT_ENTER_VALUE.value
            
        elif field == 'interval':
            interval_keyboard = [
                ['5 хвилин', '10 хвилин'],
                ['15 хвилин', '30 хвилин'],
                ['1 година', '2 години'],
                ['Власний інтервал'],
                ['🏠 Скасувати']
            ]
            await query.message.reply_text(
                "⏱️ Обери новий інтервал:",
                reply_markup=ReplyKeyboardMarkup(interval_keyboard, resize_keyboard=True)
            )
            return ConversationState.EDIT_ENTER_VALUE.value
            
        elif field == 'type':
            # For type change, we reuse the day selection logic but simplified
            # We'll just ask for days or one-time
            days_keyboard = [
                ['пн', 'вт', 'ср'],
                ['чт', 'пт', 'сб'],
                ['нд'],
                ['щодня', 'не повторювати'],
                ['✅ Підтвердити', '🏠 Скасувати']
            ]
            
            # Pre-select current days if applicable
            task = context.user_data.get('edit_task', {})
            current_days = task.get('days', [])
            if current_days:
                context.user_data['edit_days'] = list(current_days)
            else:
                context.user_data['edit_days'] = []
                
            await query.message.reply_text(
                "📅 Зміни дні нагадування:",
                reply_markup=ReplyKeyboardMarkup(days_keyboard, resize_keyboard=True)
            )
            return ConversationState.EDIT_CHOOSING_DAYS.value

    async def edit_enter_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle new value input"""
        if not update.message or not update.message.text:
            return ConversationHandler.END
            
        text = update.message.text.strip()
        if text == '🏠 Скасувати':
            await update.message.reply_text("✏️ Редагування скасовано.", reply_markup=MAIN_MARKUP)
            context.user_data.clear()
            return ConversationHandler.END
            
        field = context.user_data.get('edit_field')
        task_id = context.user_data.get('edit_task_id')
        
        updates = {}
        
        if field == 'description':
            updates['description'] = text
            
        elif field == 'times':
            valid_times, invalid_times = self.validator.parse_times(text)
            if invalid_times:
                await update.message.reply_text(
                    f"⚠️ Неправильний формат: {', '.join(invalid_times)}. Спробуй ще раз:",
                    reply_markup=CANCEL_MARKUP
                )
                return ConversationState.EDIT_ENTER_VALUE.value
            if not valid_times:
                await update.message.reply_text("⚠️ Введи хоча б один час.", reply_markup=CANCEL_MARKUP)
                return ConversationState.EDIT_ENTER_VALUE.value
            updates['times'] = valid_times
            
        elif field == 'interval':
            if text == 'Власний інтервал':
                await update.message.reply_text("⏱️ Введи інтервал у хвилинах (1-1440):", reply_markup=CANCEL_MARKUP)
                return ConversationState.EDIT_ENTER_VALUE.value
                
            interval_map = {
                '5 хвилин': 5, '10 хвилин': 10, '15 хвилин': 15,
                '30 хвилин': 30, '1 година': 60, '2 години': 120
            }
            val = interval_map.get(text)
            if val is None:
                try:
                    val = int(text)
                except ValueError:
                    await update.message.reply_text("⚠️ Введи число.", reply_markup=CANCEL_MARKUP)
                    return ConversationState.EDIT_ENTER_VALUE.value
            
            if not self.validator.validate_interval(val):
                await update.message.reply_text("⚠️ Інтервал 1-1440 хвилин.", reply_markup=CANCEL_MARKUP)
                return ConversationState.EDIT_ENTER_VALUE.value
            updates['interval_minutes'] = val

        # Apply updates
        if updates:
            await self.db.update_task(task_id, **updates)
            
            # Reschedule
            task = await self.db.get_task(task_id)
            self.reminder_manager.cancel_task(task['user_id'], task_id)
            self.reminder_manager.schedule_task(task)
            
            await update.message.reply_text(
                "✅ Завдання успішно оновлено!",
                reply_markup=MAIN_MARKUP
            )
            context.user_data.clear()
            return ConversationHandler.END
            
        return ConversationState.EDIT_ENTER_VALUE.value

    async def edit_choosing_days(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle day selection in edit mode"""
        if not update.message or not update.message.text:
            return ConversationHandler.END
            
        text = update.message.text.strip()
        if text == '🏠 Скасувати':
            await update.message.reply_text("✏️ Редагування скасовано.", reply_markup=MAIN_MARKUP)
            context.user_data.clear()
            return ConversationHandler.END
            
        if text == 'не повторювати':
            # Show options for one-time reminder: day of week or specific date
            from datetime import datetime
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
            
            return ConversationState.EDIT_CHOOSING_ONE_TIME_DATE.value

    async def edit_choosing_one_time_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle one-time date selection in edit mode"""
        if not update.message or not update.message.text:
            return ConversationHandler.END
            
        text = update.message.text.strip()
        
        if text == '🏠 Скасувати':
            await update.message.reply_text("✏️ Редагування скасовано.", reply_markup=MAIN_MARKUP)
            context.user_data.clear()
            return ConversationHandler.END
            
        if text == '📅 Вказати конкретну дату':
            await update.message.reply_text(
                "📅 Введи дату (ДД.ММ.РРРР) або дату і час (ДД.ММ.РРРР ГГ:ХХ):",
                reply_markup=CANCEL_MARKUP
            )
            context.user_data['edit_field'] = 'one_time_date'
            return ConversationState.EDIT_ENTER_VALUE.value
            
        # Check if day of week was selected
        day_options = context.user_data.get('one_time_day_options', {})
        if text in day_options:
            selected_day = day_options[text]
            task_id = context.user_data.get('edit_task_id')
            
            # Update to one-time with this day
            # We need to clear one_time_date to rely on days logic for one-time
            await self.db.update_task(task_id, days=[selected_day], is_one_time=True, one_time_date=None)
            
            # Reschedule
            task = await self.db.get_task(task_id)
            self.reminder_manager.cancel_task(task['user_id'], task_id)
            self.reminder_manager.schedule_task(task)
            
            day = DayOfWeek.from_index(selected_day)
            await update.message.reply_text(
                f"✅ Оновлено! Нагадування спрацює в {day.full if day else 'обраний день'}.",
                reply_markup=MAIN_MARKUP
            )
            context.user_data.clear()
            return ConversationHandler.END
            
        await update.message.reply_text(
            "⚠️ Будь ласка, обери день тижня або вкажи конкретну дату.",
            reply_markup=CANCEL_MARKUP
        )
        return ConversationState.EDIT_CHOOSING_ONE_TIME_DATE.value

        if text == 'щодня':
            context.user_data['edit_days'] = list(range(7))
            await update.message.reply_text("✅ Обрано щоденно. Натисни '✅ Підтвердити'.")
            return ConversationState.EDIT_CHOOSING_DAYS.value
            
        if text == '✅ Підтвердити':
            days = context.user_data.get('edit_days', [])
            if not days:
                await update.message.reply_text("⚠️ Обери хоча б один день.")
                return ConversationState.EDIT_CHOOSING_DAYS.value
                
            task_id = context.user_data.get('edit_task_id')
            
            # Update to recurring with these days
            await self.db.update_task(task_id, days=days, is_one_time=False, one_time_date=None)
            
            # Reschedule
            task = await self.db.get_task(task_id)
            self.reminder_manager.cancel_task(task['user_id'], task_id)
            self.reminder_manager.schedule_task(task)
            
            await update.message.reply_text("✅ Дні оновлено!", reply_markup=MAIN_MARKUP)
            context.user_data.clear()
            return ConversationHandler.END
            
        day = DayOfWeek.from_short(text)
        if day:
            current = context.user_data.get('edit_days', [])
            if day.index in current:
                current.remove(day.index)
            else:
                current.append(day.index)
            current.sort()
            context.user_data['edit_days'] = current
            
            day_names = [DayOfWeek.from_index(i).full for i in current]
            msg = f"✅ Обрані дні: {', '.join(day_names)}" if current else "Ще не обрано жодного дня."
            await update.message.reply_text(msg)
            
        return ConversationState.EDIT_CHOOSING_DAYS.value
