import asyncio
import logging
import threading
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from .config import TIMEZONE
from .database import DatabaseManager

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)

class DayOfWeek:
    """Days of the week mapping"""
    MONDAY = (0, 'пн', 'Понеділок', 'mon')
    TUESDAY = (1, 'вт', 'Вівторок', 'tue')
    WEDNESDAY = (2, 'ср', 'Середа', 'wed')
    THURSDAY = (3, 'чт', 'Четвер', 'thu')
    FRIDAY = (4, 'пт', 'П\'ятниця', 'fri')
    SATURDAY = (5, 'сб', 'Субота', 'sat')
    SUNDAY = (6, 'нд', 'Неділя', 'sun')
    
    def __init__(self, index: int, short: str, full: str, cron: str):
        self.index = index
        self.short = short
        self.full = full
        self.cron = cron
    
    @classmethod
    def from_short(cls, short: str) -> Optional['DayOfWeek']:
        """Get day from short name"""
        # This is a bit hacky to avoid full Enum implementation for now, 
        # but keeps compatibility with existing logic structure
        days = [
            cls(*cls.MONDAY), cls(*cls.TUESDAY), cls(*cls.WEDNESDAY),
            cls(*cls.THURSDAY), cls(*cls.FRIDAY), cls(*cls.SATURDAY), cls(*cls.SUNDAY)
        ]
        for day in days:
            if day.short == short.lower():
                return day
        return None
    
    @classmethod
    def from_index(cls, index: int) -> Optional['DayOfWeek']:
        """Get day from index"""
        days = [
            cls(*cls.MONDAY), cls(*cls.TUESDAY), cls(*cls.WEDNESDAY),
            cls(*cls.THURSDAY), cls(*cls.FRIDAY), cls(*cls.SATURDAY), cls(*cls.SUNDAY)
        ]
        for day in days:
            if day.index == index:
                return day
        return None

class ReminderManager:
    """Manages reminder scheduling and sending"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.scheduler = AsyncIOScheduler(
            timezone=TZ,
            job_defaults={
                'misfire_grace_time': 300,
                'coalesce': True,
                'max_instances': 1
            }
        )
        self.scheduler_jobs: Dict[int, Dict[int, Dict[str, str]]] = {}
        self.user_day_selections: Dict[int, List[int]] = {}
        self.active_repeat_tasks: Dict[str, List[asyncio.Task]] = {}
        self._lock = threading.Lock()
        self.application: Optional[Application] = None
    
    def start(self):
        """Start the scheduler"""
        try:
            self.scheduler.start()
            logger.info("Scheduler started")
            
            # Schedule daily reset at midnight
            self.scheduler.add_job(
                func=self.db.reset_daily_completions,
                trigger=CronTrigger(hour=0, minute=0),
                id='daily_reset',
                replace_existing=True,
                misfire_grace_time=600
            )
        except RuntimeError as e:
            if "no running event loop" in str(e):
                logger.warning("No event loop running, scheduler will start when bot runs")
            else:
                raise
    
    def set_application(self, app: Application):
        """Set the Telegram application instance"""
        self.application = app
    
    def schedule_task(self, task: Dict):
        """Schedule all reminders for a task"""
        try:
            user_id = task['user_id']
            task_id = task['task_id']
            is_one_time = task.get('is_one_time', False)
            
            with self._lock:
                if user_id not in self.scheduler_jobs:
                    self.scheduler_jobs[user_id] = {}
                if task_id not in self.scheduler_jobs[user_id]:
                    self.scheduler_jobs[user_id][task_id] = {}
            
            if is_one_time:
                self._schedule_one_time_task(task)
            else:
                self._schedule_recurring_task(task)
            
            logger.info(f"Scheduled all reminders for task {task_id}")
        except Exception as e:
            logger.error(f"Error scheduling task {task.get('task_id')}: {e}")
    
    def _schedule_one_time_task(self, task: Dict):
        """Schedule a one-time task"""
        user_id = task['user_id']
        task_id = task['task_id']
        days = task['days']
        times = task['times']
        one_time_date = task.get('one_time_date')
        
        now = datetime.now(TZ)
        
        if one_time_date:
            try:
                if len(one_time_date) == 10:  # YYYY-MM-DD
                    target_date = datetime.strptime(one_time_date, '%Y-%m-%d')
                    time_str = times[0]
                    hour, minute = map(int, time_str.split(':'))
                    target_datetime = target_date.replace(hour=hour, minute=minute, tzinfo=TZ)
                else:  # YYYY-MM-DD HH:MM
                    target_datetime = datetime.strptime(one_time_date, '%Y-%m-%d %H:%M')
                    target_datetime = target_datetime.replace(tzinfo=TZ)
                    time_str = target_datetime.strftime('%H:%M')
                
                if target_datetime <= now:
                    # If in the past, trigger immediately if not completed
                    logger.info(f"One-time task {task_id} is in the past, triggering immediately")
                    asyncio.create_task(self._send_reminder_async(user_id, task, time_str))
                    return
                
                job_id = f"reminder_{user_id}_{task_id}_date_{time_str.replace(':', '')}"
                self.scheduler.add_job(
                    func=self._send_reminder_async,
                    trigger=DateTrigger(run_date=target_datetime, timezone=TZ),
                    id=job_id,
                    args=[user_id, task, time_str],
                    replace_existing=True,
                    misfire_grace_time=300
                )
                
                instance_id = f"date_{time_str.replace(':', '')}"
                with self._lock:
                    self.scheduler_jobs[user_id][task_id][instance_id] = job_id
                
                return
            except ValueError as e:
                logger.error(f"Invalid date format for one-time task: {e}")
        
        # Fallback logic for days if no specific date (legacy support or specific flow)
        current_day = now.weekday()
        if not days:
            days = [current_day]
        
        for time_str in times:
            hour, minute = map(int, time_str.split(':'))
            
            target_datetime = None
            for day_index in days:
                days_until = (day_index - current_day) % 7
                if days_until == 0:
                    if hour > now.hour or (hour == now.hour and minute > now.minute):
                        target_datetime = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        break
                    else:
                        # If today but passed, trigger immediately
                        logger.info(f"One-time task {task_id} (today) is in the past, triggering immediately")
                        asyncio.create_task(self._send_reminder_async(user_id, task, time_str))
                        return # Assume one-time task only needs one trigger
                else:
                    target_datetime = now + timedelta(days=days_until)
                    target_datetime = target_datetime.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    break
            
            if target_datetime:
                job_id = f"reminder_{user_id}_{task_id}_{target_datetime.strftime('%Y%m%d')}_{time_str.replace(':', '')}"
                
                self.scheduler.add_job(
                    func=self._send_reminder_async,
                    trigger=DateTrigger(run_date=target_datetime, timezone=TZ),
                    id=job_id,
                    args=[user_id, task, time_str],
                    replace_existing=True,
                    misfire_grace_time=300
                )
                
                instance_id = f"{target_datetime.strftime('%Y%m%d')}_{time_str.replace(':', '')}"
                with self._lock:
                    self.scheduler_jobs[user_id][task_id][instance_id] = job_id
    
    def _schedule_recurring_task(self, task: Dict):
        """Schedule a recurring task"""
        user_id = task['user_id']
        task_id = task['task_id']
        days = task['days']
        times = task['times']
        
        now = datetime.now(TZ)
        current_day_index = now.weekday()
        
        for day_index in days:
            day = DayOfWeek.from_index(day_index)
            if not day:
                continue
            
            for time_str in times:
                hour, minute = map(int, time_str.split(':'))
                
                job_id = f"reminder_{user_id}_{task_id}_{day_index}_{time_str.replace(':', '')}"
                
                self.scheduler.add_job(
                    func=self._send_reminder_async,
                    trigger=CronTrigger(day_of_week=day.cron, hour=hour, minute=minute, timezone=TZ),
                    id=job_id,
                    args=[user_id, task, time_str],
                    replace_existing=True,
                    misfire_grace_time=300
                )
                
                instance_id = f"{day_index}_{time_str.replace(':', '')}"
                with self._lock:
                    self.scheduler_jobs[user_id][task_id][instance_id] = job_id
                
                # Check if we missed a run today
                if day_index == current_day_index:
                    task_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if task_time < now:
                        # It's today and the time has passed.
                        # CronTrigger scheduled it for next week.
                        # We should trigger it now if it's not completed.
                        logger.info(f"Recurring task {task_id} missed today's slot {time_str}, triggering catch-up")
                        asyncio.create_task(self._send_reminder_async(user_id, task, time_str))


    async def _send_reminder_async(self, user_id: int, task: Dict, reminder_time: str):
        """Send a reminder (async wrapper)"""
        try:
            # Verify task still exists
            current_task = await self.db.get_task(task['task_id'])
            if not current_task:
                return
            
            if current_task.get('is_completed'):
                return

            reminder_instance_id = f"{task['task_id']}_{reminder_time.replace(':', '')}"
            if await self.db.is_reminder_completed(user_id, task['task_id'], reminder_instance_id):
                return

            now = datetime.now(TZ)
            skip_send = False

            # Check per-reminder snooze
            snoozed_until = await self.db.get_reminder_snooze(
                user_id, task['task_id'], reminder_instance_id
            )
            if snoozed_until:
                if now < snoozed_until:
                    logger.info(
                        f"Reminder {task['task_id']} for user {user_id} "
                        f"is snoozed until {snoozed_until}, skipping send (but keeping repeats)"
                    )
                    skip_send = True
                else:
                    # Snooze expired – clear record and continue as normal
                    await self.db.clear_reminder_snooze(
                        user_id, task['task_id'], reminder_instance_id
                    )

            # Check global user-level snooze (affects all reminders)
            user_snoozed_until = await self.db.get_user_snooze(user_id)
            if user_snoozed_until:
                if now < user_snoozed_until:
                    logger.info(
                        f"All reminders for user {user_id} "
                        f"are snoozed until {user_snoozed_until}, skipping send (but keeping repeats)"
                    )
                    skip_send = True
                else:
                    await self.db.clear_user_snooze(user_id)

            # If this is the initial scheduled run (from APScheduler),
            # cancel any stale repeat tasks; for follow-up repeats we
            # keep the chain alive.
            with self._lock:
                has_repeat_tasks = reminder_instance_id in self.active_repeat_tasks
            if not has_repeat_tasks:
                self._cancel_repeat_tasks(reminder_instance_id)
            
            if not skip_send:
                await self._send_reminder_message(user_id, task, reminder_time)
            
            if not await self.db.is_reminder_completed(user_id, task['task_id'], reminder_instance_id):
                await self._schedule_next_reminder(user_id, task, reminder_time, reminder_instance_id)
        
        except Exception as e:
            logger.error(f"Error sending reminder to user {user_id}: {e}")

    async def _send_reminder_message(self, user_id: int, task: Dict, reminder_time: str):
        """Send reminder message to user"""
        if not self.application:
            return
        
        reminder_code = reminder_time.replace(':', '')
        keyboard = [[
            InlineKeyboardButton(
                "✅ Готово", 
                callback_data=f"done_{task['task_id']}_{reminder_code}",
                api_kwargs={'style': 'success'}
            ),
            InlineKeyboardButton(
                "⏰ Відкласти",
                callback_data=f"snooze_{task['task_id']}_{reminder_code}",
                api_kwargs={'style': 'primary'}
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            f"⏰ *Нагадування*\n\n"
            f"📝 {task['description']}\n\n"
            f"Час: {reminder_time}\n\n"
            f"Будь ласка, познач як виконане, коли завершиш:"
        )
        
        await self.application.bot.send_message(
            chat_id=user_id,
            text=message_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    async def _schedule_next_reminder(self, user_id: int, task: Dict, 
                                     reminder_time: str, reminder_instance_id: str):
        """Schedule the next reminder after interval"""
        interval_minutes = task['interval_minutes']
        
        async def send_next():
            try:
                await asyncio.sleep(interval_minutes * 60)
                if not await self.db.is_reminder_completed(user_id, task['task_id'], reminder_instance_id):
                    await self._send_reminder_async(user_id, task, reminder_time)
            except asyncio.CancelledError:
                raise
            finally:
                with self._lock:
                    if reminder_instance_id in self.active_repeat_tasks:
                        self.active_repeat_tasks[reminder_instance_id] = [
                            t for t in self.active_repeat_tasks[reminder_instance_id] 
                            if not t.done()
                        ]
                        if not self.active_repeat_tasks[reminder_instance_id]:
                            del self.active_repeat_tasks[reminder_instance_id]
        
        repeat_task = asyncio.create_task(send_next())
        
        with self._lock:
            if reminder_instance_id not in self.active_repeat_tasks:
                self.active_repeat_tasks[reminder_instance_id] = []
            self.active_repeat_tasks[reminder_instance_id].append(repeat_task)

    def _cancel_repeat_tasks(self, reminder_instance_id: str):
        """Cancel all active repeat tasks for a reminder instance"""
        with self._lock:
            if reminder_instance_id in self.active_repeat_tasks:
                tasks_to_cancel = self.active_repeat_tasks[reminder_instance_id]
                for task in tasks_to_cancel:
                    if not task.done():
                        task.cancel()
                del self.active_repeat_tasks[reminder_instance_id]

    def cancel_task(self, user_id: int, task_id: int):
        """Cancel all scheduled jobs and repeat tasks for a task"""
        with self._lock:
            if user_id not in self.scheduler_jobs:
                return
            
            if task_id not in self.scheduler_jobs[user_id]:
                return
            
            for instance_id, job_id in self.scheduler_jobs[user_id][task_id].items():
                try:
                    self.scheduler.remove_job(job_id)
                except Exception:
                    pass
                
                reminder_instance_id = f"{task_id}_{instance_id.split('_')[-1]}" if '_' in instance_id else f"{task_id}_{instance_id}"
                if reminder_instance_id in self.active_repeat_tasks:
                    tasks_to_cancel = self.active_repeat_tasks[reminder_instance_id]
                    for task in tasks_to_cancel:
                        if not task.done():
                            task.cancel()
                    del self.active_repeat_tasks[reminder_instance_id]
            
            tasks_to_remove = []
            for reminder_instance_id, tasks in self.active_repeat_tasks.items():
                if reminder_instance_id.startswith(f"{task_id}_"):
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    tasks_to_remove.append(reminder_instance_id)
            
            for reminder_instance_id in tasks_to_remove:
                del self.active_repeat_tasks[reminder_instance_id]
            
            del self.scheduler_jobs[user_id][task_id]
