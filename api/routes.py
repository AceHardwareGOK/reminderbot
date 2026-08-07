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
    
    completed_today_count = 0
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

    now_hm = now.strftime('%H:%M')

    for task in tasks:
        task_id = task['task_id']
        times = task.get('times', [])
        is_one_time = task.get('is_one_time', False)
        one_time_date = task.get('one_time_date', '')
        
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
            elif t_str > now_hm:
                if not next_found:
                    statuses.append({"time": t_str, "status": "next", "label": "Наступне"})
                    next_found = True
                else:
                    statuses.append({"time": t_str, "status": "upcoming", "label": "Очікується"})
            else:
                statuses.append({"time": t_str, "status": "past", "label": "Пропущено"})

        if not next_found:
            past_indices = [i for i, s in enumerate(statuses) if s["status"] == "past"]
            if past_indices:
                statuses[past_indices[-1]]["status"] = "next"
                statuses[past_indices[-1]]["label"] = "Наступне (пропущено)"
                
        task['time_statuses'] = statuses

    today_index = now.weekday()
    today_active_count = 0
    for t in tasks:
        if not t.get('is_one_time') and today_index in t.get('days', []):
            today_active_count += 1
        elif t.get('is_one_time') and t.get('one_time_date'):
            if today_str in str(t.get('one_time_date', '')):
                today_active_count += 1

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
    """Відмітити завдання виконаним з гарантованим видаленням одноразових завдань"""
    task = await db_manager.get_task(task_id)
    if not task or task["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    is_one_time = task.get("is_one_time", False)
    times = task.get("times", [])
    one_time_date = task.get("one_time_date", "")

    # Збираємо всі можливі варіанти ідентифікаторів екземпляра
    rem_inst_ids = []
    if reminder_instance_id:
        rem_inst_ids.append(reminder_instance_id)

    for t in times:
        t_clean = t.replace(":", "")
        rem_inst_ids.append(f"{task_id}_{t_clean}")
        if is_one_time and one_time_date:
            for d in one_time_date.split(","):
                d_clean = d.strip()[:10].replace("-", "")
                if d_clean:
                    rem_inst_ids.append(f"{task_id}_{d_clean}_{t_clean}")
    
    rem_inst_ids.append(f"inst_{task_id}")

    # 1. Позначаємо виконаним для всіх варіацій ключа
    for inst_id in set(rem_inst_ids):
        await db_manager.mark_reminder_completed(user_id, task_id, inst_id)
        if reminder_manager:
            try:
                reminder_manager.cancel_repeat_tasks(inst_id)
            except Exception:
                pass

    # 2. Якщо це одноразове завдання — знімаємо з розкладу та БЕЗУМОВНО видаляємо з БД
    if is_one_time:
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


@router.post("/tasks/{task_id}/snooze")
async def snooze_task(
    task_id: int,
    payload: SnoozeRequest,
    user_id: int = Depends(get_current_user)
):
    """Відкласти конкретне завдання на N хвилин для всіх варіацій ключів"""
    task = await db_manager.get_task(task_id)
    if not task or task["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from core.config import TIMEZONE

    now = datetime.now(ZoneInfo(TIMEZONE))
    snoozed_until = now + timedelta(minutes=payload.minutes)

    times = task.get("times", [])
    is_one_time = task.get("is_one_time", False)
    one_time_date = task.get("one_time_date", "")

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

    return {"status": "ok", "snoozed_until": snoozed_until.isoformat()}


@router.post("/snooze-clear")
async def clear_snooze_all(
    user_id: int = Depends(get_current_user)
):
    """Очистити глобальне відкладення користувача"""
    await db_manager.clear_user_snooze(user_id)
    return {"status": "ok", "cleared": True}

