import aiosqlite
import logging
from typing import List, Dict, Optional
from datetime import datetime
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo
from .config import DB_PATH, TIMEZONE

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)

class DatabaseManager:
    """Async database manager using aiosqlite"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
    
    @asynccontextmanager
    async def _get_connection(self):
        """Get a database connection with automatic cleanup"""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    async def init_database(self):
        """Initialize database schema"""
        async with self._get_connection() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    days TEXT NOT NULL,
                    times TEXT NOT NULL,
                    interval_minutes INTEGER NOT NULL,
                    is_one_time BOOLEAN DEFAULT 0,
                    is_completed BOOLEAN DEFAULT 0,
                    one_time_date TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Add one_time_date column if it doesn't exist (for existing databases)
            try:
                await conn.execute('ALTER TABLE tasks ADD COLUMN one_time_date TEXT')
            except aiosqlite.OperationalError:
                pass  # Column already exists
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS completed_reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    task_id INTEGER NOT NULL,
                    reminder_instance_id TEXT NOT NULL,
                    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, task_id, reminder_instance_id)
                )
            ''')
            
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_tasks_user 
                ON tasks(user_id)
            ''')
            
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_completed_user_task 
                ON completed_reminders(user_id, task_id)
            ''')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS snoozed_reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    task_id INTEGER NOT NULL,
                    reminder_instance_id TEXT NOT NULL,
                    snoozed_until TIMESTAMP NOT NULL,
                    UNIQUE(user_id, task_id, reminder_instance_id)
                )
            ''')
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_snoozed_user_task 
                ON snoozed_reminders(user_id, task_id, reminder_instance_id)
            ''')
            
            await conn.commit()

    async def add_task(self, user_id: int, description: str, days: List[int], 
                 times: List[str], interval_minutes: int, is_one_time: bool = False,
                 one_time_date: Optional[str] = None) -> int:
        """Add a new task"""
        async with self._get_connection() as conn:
            cursor = await conn.execute('''
                INSERT INTO tasks (user_id, description, days, times, interval_minutes, is_one_time, one_time_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, description, ','.join(map(str, days)), 
                  ','.join(times), interval_minutes, is_one_time, one_time_date))
            await conn.commit()
            return cursor.lastrowid

    async def get_task(self, task_id: int) -> Optional[Dict]:
        """Get a task by ID"""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                'SELECT * FROM tasks WHERE task_id = ?', 
                (task_id,)
            )
            row = await cursor.fetchone()
            return self._row_to_task(row) if row else None

    async def delete_task(self, task_id: int) -> bool:
        """Delete a task"""
        async with self._get_connection() as conn:
            cursor = await conn.execute('DELETE FROM tasks WHERE task_id = ?', (task_id,))
            await conn.commit()
            return cursor.rowcount > 0

    async def update_task(self, task_id: int, **kwargs):
        """Update task fields"""
        valid_fields = {'description', 'days', 'times', 'interval_minutes', 'is_one_time', 'one_time_date'}
        updates = []
        values = []
        
        for key, value in kwargs.items():
            if key not in valid_fields:
                continue
            
            if key == 'days':
                # Ensure list of ints
                if isinstance(value, list):
                    value = ','.join(map(str, value))
            elif key == 'times':
                # Ensure list of strings
                if isinstance(value, list):
                    value = ','.join(value)
                
            updates.append(f"{key} = ?")
            values.append(value)
            
        if not updates:
            return
            
        values.append(task_id)
        
        async with self._get_connection() as conn:
            await conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?",
                values
            )
            await conn.commit()

    async def get_user_tasks(self, user_id: int, include_completed: bool = False) -> List[Dict]:
        """Get all tasks for a user"""
        async with self._get_connection() as conn:
            query = 'SELECT * FROM tasks WHERE user_id = ?'
            if not include_completed:
                query += ' AND is_completed = 0'
            
            cursor = await conn.execute(query, (user_id,))
            rows = await cursor.fetchall()
            return [self._row_to_task(row) for row in rows]

    async def mark_reminder_completed(self, user_id: int, task_id: int, 
                               reminder_instance_id: str) -> bool:
        """Mark a specific reminder instance as completed"""
        async with self._get_connection() as conn:
            try:
                await conn.execute('''
                    INSERT INTO completed_reminders (user_id, task_id, reminder_instance_id)
                    VALUES (?, ?, ?)
                ''', (user_id, task_id, reminder_instance_id))
                await conn.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def is_reminder_completed(self, user_id: int, task_id: int, 
                             reminder_instance_id: str) -> bool:
        """Check if a reminder instance is completed"""
        async with self._get_connection() as conn:
            cursor = await conn.execute('''
                SELECT completed_at FROM completed_reminders 
                WHERE user_id = ? AND task_id = ? AND reminder_instance_id = ?
            ''', (user_id, task_id, reminder_instance_id))
            row = await cursor.fetchone()
            
            if not row:
                return False
            
            completed_at_str = row['completed_at']
            completed_at = self._parse_date(completed_at_str)
            if not completed_at:
                return True 

            now = datetime.now(TZ)
            today = now.date()
            completion_date = completed_at.date()
            
            reminder_hour = None
            try:
                parts = reminder_instance_id.split('_')
                if len(parts) >= 2:
                    time_part = parts[-1]
                    if len(time_part) == 4 and time_part.isdigit():
                        reminder_hour = int(time_part[:2])
            except (ValueError, IndexError):
                pass

            if completion_date < today:
                await conn.execute('''
                    DELETE FROM completed_reminders 
                    WHERE user_id = ? AND task_id = ? AND reminder_instance_id = ?
                ''', (user_id, task_id, reminder_instance_id))
                await conn.commit()
                return False
            elif completion_date == today:
                if reminder_hour is not None and reminder_hour >= 22:
                    current_hour = now.hour
                    if current_hour < reminder_hour and completed_at.hour < 6:
                        return True
                    elif current_hour >= reminder_hour and completed_at.hour < 6:
                        await conn.execute('''
                            DELETE FROM completed_reminders 
                            WHERE user_id = ? AND task_id = ? AND reminder_instance_id = ?
                        ''', (user_id, task_id, reminder_instance_id))
                        await conn.commit()
                        return False
                    elif completed_at.hour < reminder_hour and current_hour >= reminder_hour:
                        await conn.execute('''
                            DELETE FROM completed_reminders 
                            WHERE user_id = ? AND task_id = ? AND reminder_instance_id = ?
                        ''', (user_id, task_id, reminder_instance_id))
                        await conn.commit()
                        return False
                return True
            else:
                await conn.execute('''
                    DELETE FROM completed_reminders 
                    WHERE user_id = ? AND task_id = ? AND reminder_instance_id = ?
                ''', (user_id, task_id, reminder_instance_id))
                await conn.commit()
                return False

    async def reset_daily_completions(self):
        """Reset all completed reminders"""
        async with self._get_connection() as conn:
            cursor = await conn.execute('SELECT COUNT(*) FROM completed_reminders')
            count_before = (await cursor.fetchone())[0]
            await conn.execute('DELETE FROM completed_reminders')
            await conn.commit()
            logger.info(f"Daily completions reset: deleted {count_before} completed reminder records")

    def _row_to_task(self, row: aiosqlite.Row) -> Dict:
        """Convert database row to task dictionary"""
        one_time_date = None
        try:
            value = row['one_time_date']
            if value:
                one_time_date = value
        except (KeyError, IndexError):
            pass
        
        return {
            'task_id': row['task_id'],
            'user_id': row['user_id'],
            'description': row['description'],
            'days': [int(d) for d in row['days'].split(',') if d],
            'times': row['times'].split(','),
            'interval_minutes': row['interval_minutes'],
            'is_one_time': bool(row['is_one_time']),
            'is_completed': bool(row['is_completed']),
            'one_time_date': one_time_date
        }

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Helper to parse date strings"""
        if isinstance(date_str, datetime):
            return date_str
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except ValueError:
            try:
                return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d')
                except ValueError:
                    return None

    # ========== SNOOZE SUPPORT ==========

    async def set_reminder_snooze(
        self,
        user_id: int,
        task_id: int,
        reminder_instance_id: str,
        snoozed_until: datetime,
    ) -> None:
        """Set or update snooze for a specific reminder instance."""
        async with self._get_connection() as conn:
            # Store as ISO string (with timezone if present)
            value = snoozed_until.isoformat()
            try:
                await conn.execute(
                    '''
                    INSERT INTO snoozed_reminders (user_id, task_id, reminder_instance_id, snoozed_until)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, task_id, reminder_instance_id)
                    DO UPDATE SET snoozed_until = excluded.snoozed_until
                    ''',
                    (user_id, task_id, reminder_instance_id, value),
                )
            except aiosqlite.OperationalError:
                # Fallback for SQLite versions without ON CONFLICT support
                await conn.execute(
                    '''
                    DELETE FROM snoozed_reminders
                    WHERE user_id = ? AND task_id = ? AND reminder_instance_id = ?
                    ''',
                    (user_id, task_id, reminder_instance_id),
                )
                await conn.execute(
                    '''
                    INSERT INTO snoozed_reminders (user_id, task_id, reminder_instance_id, snoozed_until)
                    VALUES (?, ?, ?, ?)
                    ''',
                    (user_id, task_id, reminder_instance_id, value),
                )
            await conn.commit()

    async def get_reminder_snooze(
        self,
        user_id: int,
        task_id: int,
        reminder_instance_id: str,
    ) -> Optional[datetime]:
        """Get snooze time for a specific reminder instance, if any."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                '''
                SELECT snoozed_until FROM snoozed_reminders
                WHERE user_id = ? AND task_id = ? AND reminder_instance_id = ?
                ''',
                (user_id, task_id, reminder_instance_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return self._parse_date(row['snoozed_until'])

    async def clear_reminder_snooze(
        self,
        user_id: int,
        task_id: int,
        reminder_instance_id: str,
    ) -> None:
        """Clear snooze for a specific reminder instance."""
        async with self._get_connection() as conn:
            await conn.execute(
                '''
                DELETE FROM snoozed_reminders
                WHERE user_id = ? AND task_id = ? AND reminder_instance_id = ?
                ''',
                (user_id, task_id, reminder_instance_id),
            )
            await conn.commit()

    async def set_user_snooze(self, user_id: int, snoozed_until: datetime) -> None:
        """Set or update global snooze for all reminders of a user."""
        # Use task_id = 0 and reminder_instance_id='*' as a convention for global snooze
        await self.set_reminder_snooze(
            user_id=user_id,
            task_id=0,
            reminder_instance_id='*',
            snoozed_until=snoozed_until,
        )

    async def get_user_snooze(self, user_id: int) -> Optional[datetime]:
        """Get global snooze for user, if any."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                '''
                SELECT snoozed_until FROM snoozed_reminders
                WHERE user_id = ? AND task_id = 0 AND reminder_instance_id = '*'
                ''',
                (user_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return self._parse_date(row['snoozed_until'])

    async def clear_user_snooze(self, user_id: int) -> None:
        """Clear global snooze for user."""
        async with self._get_connection() as conn:
            await conn.execute(
                '''
                DELETE FROM snoozed_reminders
                WHERE user_id = ? AND task_id = 0 AND reminder_instance_id = '*'
                ''',
                (user_id,),
            )
            await conn.commit()
