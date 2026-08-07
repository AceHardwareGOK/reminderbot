from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Optional
from pydantic import BaseModel, Field

from api.auth import get_current_user
from core.database import DatabaseManager

router = APIRouter(prefix="/api")

# Глобальні екземпляри БД та ReminderManager будуть ініціалізовані при старті
db_manager = DatabaseManager()
reminder_manager = None

def set_reminder_manager(rm):
    global reminder_manager
    reminder_manager = rm


class TaskCreateRequest(BaseModel):
    description: str = Field(..., min_length=1, description="Опис завдання")
    days: List[int] = Field(..., description="Дні тижня [0-6] або [0]")
    times: List[str] = Field(..., description="Масив часів ['09:00', '14:30']")
    interval_minutes: int = Field(default=0, ge=0)
    is_one_time: bool = Field(default=False)
    one_time_date: Optional[str] = Field(default=None, description="Строка дат через кому або ISO")


class TaskUpdateRequest(BaseModel):
    description: Optional[str] = None
    days: Optional[List[int]] = None
    times: Optional[List[str]] = None
    interval_minutes: Optional[int] = None
    is_one_time: Optional[bool] = None
    one_time_date: Optional[str] = None


@router.get("/tasks")
async def get_tasks(user_id: int = Depends(get_current_user)):
    """Отримати всі нагадування поточного користувача та статистику виконання на сьогодні"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from core.config import TIMEZONE

    tasks = await db_manager.get_user_tasks(user_id=user_id, include_completed=False)
    
    now = datetime.now(ZoneInfo(TIMEZONE))
    today_date = now.date()
    today_str = now.strftime('%Y-%m-%d')
    
    snoozed_map = {}
    async with db_manager._get_connection() as conn:
        cursor = await conn.execute('''
            SELECT completed_at, reminder_instance_id
            FROM completed_reminders 
            WHERE user_id = ?
        ''', (user_id,))
        rows = await cursor.fetchall()
        
        seen_insts = set()
        for r in rows:
            c_at_str = r['completed_at']
            c_at = db_manager._parse_date(c_at_str)
            if c_at and c_at.date() == today_date:
                seen_insts.add(r['reminder_instance_id'])
        completed_today_count = len(seen_insts)

        cursor_s = await conn.execute('''
            SELECT task_id, snoozed_until
            FROM snoozed_reminders 
            WHERE user_id = ?
        ''', (user_id,))
        s_rows = await cursor_s.fetchall()
        for sr in s_rows:
            sn_dt = db_manager._parse_date(sr['snoozed_until'])
            if sn_dt and sn_dt > now:
                t_id = sr['task_id']
                if t_id not in snoozed_map or sn_dt > snoozed_map[t_id]:
                    snoozed_map[t_id] = sn_dt

    now_hm = now.strftime('%H:%M')

    for task in tasks:
        task_id = task['task_id']
        times = task.get('times', [])
        is_one_time = task.get('is_one_time', False)
        one_time_date = task.get('one_time_date', '')

        if task_id in snoozed_map:
            sn_dt = snoozed_map[task_id]
            mins_left = max(1, int((sn_dt - now).total_seconds() / 60))
            sn_time_str = sn_dt.strftime('%H:%M')
            task['is_snoozed'] = True
            task['snooze_time'] = sn_time_str
            task['snooze_minutes_left'] = mins_left
            task['snooze_display'] = f"{sn_time_str} (через {mins_left} хв)"
        else:
            task['is_snoozed'] = False
            task['snooze_time'] = None
            task['snooze_minutes_left'] = None
            task['snooze_display'] = None

        is_future_task = False
        if is_one_time and one_time_date:
            dates = [d.strip()[:10] for d in str(one_time_date).split(',') if d.strip()]
            norm_dates = []
            for d in dates:
                if '.' in d:
                    parts = d.split('.')
                    if len(parts) == 3:
                        norm_dates.append(f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}")
                    else:
                        norm_dates.append(d)
                else:
                    norm_dates.append(d)
            if norm_dates and min(norm_dates) > today_str:
                is_future_task = True
        
        statuses = []
        next_found = False
        sorted_times = sorted(times)
        
        for t_str in sorted_times:
            t_clean = t_str.replace(":", "")
            inst_id_simple = f"{task_id}_{t_clean}"
            
            is_comp = inst_id_simple in seen_insts or f"inst_{task_id}" in seen_insts
            if is_one_time and one_time_date:
                for d in str(one_time_date).split(','):
                    d_clean = d.strip()[:10].replace("-", "")
                    if d_clean and f"{task_id}_{d_clean}_{t_clean}" in seen_insts:
                        is_comp = True
                        break
            
            if is_comp:
                statuses.append({"time": t_str, "status": "completed", "label": "Виконано"})
            elif is_future_task:
                if not next_found:
                    statuses.append({"time": t_str, "status": "next", "label": "Наступне"})
                    next_found = True
                else:
                    statuses.append({"time": t_str, "status": "upcoming", "label": "Очікується"})
            elif t_str > now_hm:
                if not next_found:
                    statuses.append({"time": t_str, "status": "next", "label": "Наступне"})
                    next_found = True
                else:
                    statuses.append({"time": t_str, "status": "upcoming", "label": "Очікується"})
            else:
                statuses.append({"time": t_str, "status": "past", "label": "Пропущено"})

        if not next_found and not is_future_task:
            past_indices = [i for i, s in enumerate(statuses) if s["status"] == "past"]
            if past_indices:
                statuses[past_indices[-1]]["status"] = "next"
                statuses[past_indices[-1]]["label"] = "Наступне (пропущено)"
                
        task['time_statuses'] = statuses

    today_index = now.weekday()
    today_active_count = 0
    for t in tasks:
        days_list = t.get('days', [])
        if not t.get('is_one_time') and (today_index in days_list or str(today_index) in map(str, days_list)):
            today_active_count += 1
        elif t.get('is_one_time') and t.get('one_time_date'):
            ot_dates = str(t.get('one_time_date', '')).split(',')
            for d in ot_dates:
                d_clean = d.strip()[:10]
                if d_clean == today_str:
                    today_active_count += 1
                    break
                elif '.' in d_clean:
                    parts = d_clean.split('.')
                    if len(parts) == 3:
                        formatted = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                        if formatted == today_str:
                            today_active_count += 1
                            break

    total_today = completed_today_count + today_active_count
    progress_percent = int((completed_today_count / total_today * 100)) if total_today > 0 else (100 if completed_today_count > 0 else 0)

    return {
        "status": "ok", 
        "tasks": tasks,
        "completed_today_count": completed_today_count,
        "total_today_count": total_today,
        "progress_percent": progress_percent
    }




@router.post("/tasks")
async def create_task(
    payload: TaskCreateRequest,
    user_id: int = Depends(get_current_user)
):
    """Створити нове завдання з Web App"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from core.config import TIMEZONE

    times = [t.strip() for t in payload.times if t.strip()]
    if not times:
        times = ["09:00"]

    days = payload.days
    if not payload.is_one_time and not days:
        days = [0, 1, 2, 3, 4, 5, 6]
    elif payload.is_one_time and not days:
        days = [0]

    one_time_date = payload.one_time_date
    if payload.is_one_time and not one_time_date:
        now = datetime.now(ZoneInfo(TIMEZONE))
        one_time_date = now.strftime("%Y-%m-%d")

    task_id = await db_manager.add_task(
        user_id=user_id,
        description=payload.description.strip(),
        days=days,
        times=times,
        interval_minutes=payload.interval_minutes,
        is_one_time=payload.is_one_time,
        one_time_date=one_time_date
    )

    task = await db_manager.get_task(task_id)

    # Якщо ReminderManager підключено, плануємо нагадування
    if reminder_manager and task:
        try:
            reminder_manager.schedule_task(task)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error scheduling task {task_id}: {e}")

    return {"status": "ok", "task": task}



@router.put("/tasks/{task_id}")
async def update_task(
    task_id: int,
    payload: TaskUpdateRequest,
    user_id: int = Depends(get_current_user)
):
    """Оновити нагадування"""
    task = await db_manager.get_task(task_id)
    if not task or task["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = payload.dict(exclude_unset=True)
    if update_data:
        await db_manager.update_task(task_id, **update_data)

    updated_task = await db_manager.get_task(task_id)

    if reminder_manager and updated_task:
        try:
            reminder_manager.cancel_task(user_id, task_id)
            reminder_manager.schedule_task(updated_task)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error updating task schedule {task_id}: {e}")

    return {"status": "ok", "task": updated_task}


@router.api_route("/tasks/{task_id}/delete", methods=["POST", "DELETE"])
@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int,
    user_id: int = Depends(get_current_user)
):
    """Видалити нагадування"""
    task = await db_manager.get_task(task_id)
    if not task or task["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    await db_manager.delete_task(task_id)

    if reminder_manager:
        try:
            reminder_manager.cancel_task(user_id, task_id)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error canceling task schedule {task_id}: {e}")

    return {"status": "ok", "deleted": True}




@router.post("/tasks/{task_id}/complete")
async def complete_task_instance(
    task_id: int,
    reminder_instance_id: Optional[str] = Body(None, embed=True),
    user_id: int = Depends(get_current_user)
):
    """Відмітити конкретний слот часу завдання або найближчий актуальний слот"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from core.config import TIMEZONE

    task = await db_manager.get_task(task_id)
    if not task or task["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    is_one_time = task.get("is_one_time", False)
    times = task.get("times", [])
    one_time_date = task.get("one_time_date", "")

    target_time_clean = None
    if reminder_instance_id:
        parts = reminder_instance_id.split("_")
        if len(parts) >= 2:
            target_time_clean = parts[-1]

    if not target_time_clean and times:
        now = datetime.now(ZoneInfo(TIMEZONE))
        now_hm = now.strftime('%H:%M')
        
        seen_insts = set()
        async with db_manager._get_connection() as conn:
            cursor = await conn.execute('''
                SELECT reminder_instance_id FROM completed_reminders 
                WHERE user_id = ? AND task_id = ?
            ''', (user_id, task_id))
            rows = await cursor.fetchall()
            for r in rows:
                seen_insts.add(r['reminder_instance_id'])

        sorted_times = sorted(times)
        chosen_time = None
        
        for t in sorted_times:
            t_clean = t.replace(":", "")
            inst_id_simple = f"{task_id}_{t_clean}"
            if inst_id_simple not in seen_insts:
                chosen_time = t
                if t > now_hm:
                    break
        
        if not chosen_time:
            chosen_time = sorted_times[0]
            
        target_time_clean = chosen_time.replace(":", "")
        reminder_instance_id = f"{task_id}_{target_time_clean}"

    rem_inst_ids = []
    if reminder_instance_id:
        rem_inst_ids.append(reminder_instance_id)

    if target_time_clean:
        rem_inst_ids.append(f"{task_id}_{target_time_clean}")
        if is_one_time and one_time_date:
            for d in str(one_time_date).split(","):
                d_clean = d.strip()[:10].replace("-", "")
                if d_clean:
                    rem_inst_ids.append(f"{task_id}_{d_clean}_{target_time_clean}")

    for inst_id in set(rem_inst_ids):
        await db_manager.mark_reminder_completed(user_id, task_id, inst_id)
        if reminder_manager:
            try:
                reminder_manager.cancel_repeat_tasks(inst_id)
            except Exception:
                pass

    # Автоматично позначаємо пов'язані сповіщення прочитаними вnotifications_log
    try:
        async with db_manager._get_connection() as conn:
            await conn.execute(
                "UPDATE notifications_log SET is_read = 1 WHERE user_id = ? AND task_id = ?",
                (user_id, task_id)
            )
            await conn.commit()
    except Exception:
        pass

    if is_one_time:
        has_remaining = True
        if reminder_manager:
            has_remaining = await reminder_manager.has_remaining_one_time_slots(user_id, task)
            
        if not has_remaining:
            if reminder_manager:
                try:
                    reminder_manager.cancel_task(user_id, task_id)
                except Exception:
                    pass
            await db_manager.delete_task(task_id)
            return {"status": "ok", "completed": True, "deleted": True}

    return {"status": "ok", "completed": True, "deleted": False}




class SnoozeRequest(BaseModel):
    minutes: int = Field(default=30, ge=1)
    is_repeat: Optional[bool] = False


@router.post("/tasks/{task_id}/snooze")
async def snooze_task(
    task_id: int,
    payload: SnoozeRequest,
    user_id: int = Depends(get_current_user)
):
    """Відкласти або повторити конкретне завдання на N хвилин"""
    task = await db_manager.get_task(task_id)
    if not task or task["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from core.config import TIMEZONE

    now = datetime.now(ZoneInfo(TIMEZONE))

    times = task.get("times", [])
    is_one_time = task.get("is_one_time", False)
    one_time_date = task.get("one_time_date", "")
    interval_minutes = task.get("interval_minutes", 0)

    # 1. Знаходимо базовий час слоту (base_dt) від самого нагадування
    base_date = now.date()
    if is_one_time and one_time_date:
        dates = [d.strip()[:10] for d in str(one_time_date).split(',') if d.strip()]
        if dates:
            try:
                base_date = datetime.strptime(dates[0], '%Y-%m-%d').date()
            except Exception:
                pass

    sorted_times = sorted(times) if times else ["09:00"]
    now_hm = now.strftime('%H:%M')
    target_time_str = sorted_times[0]
    for t in sorted_times:
        if t >= now_hm:
            target_time_str = t
            break

    try:
        h, m = map(int, target_time_str.split(':'))
        base_dt = datetime(base_date.year, base_date.month, base_date.day, h, m, tzinfo=ZoneInfo(TIMEZONE))
    except Exception:
        base_dt = now

    # 2. Якщо це повторення (is_repeat) - від моменту натискання (now), якщо відкладання - від часу нагадування (base_dt)
    is_repeat_action = payload.is_repeat or (interval_minutes == 0 and base_dt <= now)

    if is_repeat_action:
        snoozed_until = now + timedelta(minutes=payload.minutes)
    else:
        snoozed_until = base_dt + timedelta(minutes=payload.minutes)
        if snoozed_until <= now:
            snoozed_until = now + timedelta(minutes=payload.minutes)

    snooze_delay_minutes = max(1, int((snoozed_until - now).total_seconds() / 60))

    inst_ids = [f"{task_id}_snooze", f"inst_{task_id}"]
    for t in times:
        t_clean = t.replace(":", "")
        inst_ids.append(f"{task_id}_{t_clean}")
        if is_one_time and one_time_date:
            for d in one_time_date.split(","):
                d_clean = d.strip()[:10].replace("-", "")
                if d_clean:
                    inst_ids.append(f"{task_id}_{d_clean}_{t_clean}")

    for inst_id in set(inst_ids):
        await db_manager.set_reminder_snooze(user_id, task_id, inst_id, snoozed_until)

    if reminder_manager:
        try:
            reminder_manager.schedule_snooze_reminder(user_id, task, snooze_delay_minutes)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error scheduling snooze job for task {task_id}: {e}")

    try:
        async with db_manager._get_connection() as conn:
            await conn.execute(
                "UPDATE notifications_log SET is_read = 1 WHERE user_id = ? AND task_id = ?",
                (user_id, task_id)
            )
            await conn.commit()
    except Exception:
        pass

    return {"status": "ok", "snoozed_until": snoozed_until.isoformat()}



@router.post("/snooze-all")
async def snooze_all_tasks(
    payload: SnoozeRequest,
    user_id: int = Depends(get_current_user)
):
    """Глобально відкласти всі нагадування користувача на N хвилин"""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from core.config import TIMEZONE

    now = datetime.now(ZoneInfo(TIMEZONE))
    snoozed_until = now + timedelta(minutes=payload.minutes)
    
    await db_manager.set_user_snooze(user_id, snoozed_until)

    if reminder_manager:
        try:
            user_tasks = await db_manager.get_user_tasks(user_id)
            for t in user_tasks:
                if not t.get('is_completed'):
                    reminder_manager.schedule_snooze_reminder(user_id, t, payload.minutes)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error scheduling snooze-all jobs: {e}")

    return {"status": "ok", "snoozed_until": snoozed_until.isoformat()}


@router.post("/snooze-clear")
async def clear_snooze_all(
    user_id: int = Depends(get_current_user)
):
    """Очистити глобальне відкладення користувача"""
    await db_manager.clear_user_snooze(user_id)
    return {"status": "ok", "cleared": True}


# --- Notifications API Endpoints ---
@router.get("/notifications")
async def get_notifications(
    limit: int = 50,
    user_id: int = Depends(get_current_user)
):
    """Отримати сповіщення з точним розпізнаванням статусу виконання"""
    items = await db_manager.get_notifications(user_id=user_id, limit=limit)
    unread_count = await db_manager.get_unread_notifications_count(user_id=user_id)

    # 1. Збираємо всі існуючі task_id користувача та їх прапорець is_completed
    existing_tasks = {}
    async with db_manager._get_connection() as conn:
        cursor = await conn.execute(
            "SELECT task_id, is_completed FROM tasks WHERE user_id = ?",
            (user_id,)
        )
        rows = await cursor.fetchall()
        for r in rows:
            existing_tasks[r['task_id']] = bool(r['is_completed'])

    # 2. Збираємо всі виконані екземпляри нагадувань з completed_reminders
    completed_set = set()
    async with db_manager._get_connection() as conn:
        cursor = await conn.execute(
            "SELECT task_id, reminder_instance_id FROM completed_reminders WHERE user_id = ?",
            (user_id,)
        )
        rows = await cursor.fetchall()
        for r in rows:
            completed_set.add((r['task_id'], str(r['reminder_instance_id'])))

    for item in items:
        t_id = item.get('task_id')
        r_inst = str(item.get('reminder_instance_id') or '')
        
        # Якщо завдання вже відсутнє в існуючих tasks (було одноразовим і автовидалилося після виконання)
        # або в tasks воно позначене is_completed = True
        if t_id not in existing_tasks or existing_tasks.get(t_id) is True:
            item['is_completed'] = True
            continue

        # Інакше перевіряємо completed_reminders (точний чи нормалізований збіг часу)
        is_done = (t_id, r_inst) in completed_set
        if not is_done and r_inst:
            # Нормалізуємо час без двокрапок (наприклад "09:00" -> "0900")
            time_clean = r_inst.split('_')[0].replace(':', '')
            for (c_task_id, c_inst_id) in completed_set:
                c_inst_clean = c_inst_id.replace(':', '')
                if c_task_id == t_id and (time_clean in c_inst_clean or c_inst_clean in r_inst.replace(':', '')):
                    is_done = True
                    break

        item['is_completed'] = is_done

    active_unread_count = sum(1 for item in items if not item.get('is_read') and not item.get('is_completed'))

    return {
        "status": "ok",
        "notifications": items,
        "unread_count": active_unread_count
    }

@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    user_id: int = Depends(get_current_user)
):
    """Позначити сповіщення як прочитане"""
    await db_manager.mark_notification_read(user_id=user_id, notification_id=notification_id)
    unread_count = await db_manager.get_unread_notifications_count(user_id=user_id)
    return {"status": "ok", "unread_count": unread_count}

@router.post("/notifications/read_all")
async def mark_all_notifications_read(
    user_id: int = Depends(get_current_user)
):
    """Позначити всі сповіщення як прочитані"""
    await db_manager.mark_all_notifications_read(user_id=user_id)
    return {"status": "ok", "unread_count": 0}

@router.post("/notifications/clear")
async def clear_notifications(
    user_id: int = Depends(get_current_user)
):
    """Очистити історію сповіщень"""
    await db_manager.clear_notifications(user_id=user_id)
    return {"status": "ok", "cleared": True}

