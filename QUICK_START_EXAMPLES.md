# Приклади коду для швидкого старту

## 1. FastAPI додаток (api/main.py)

```python
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from api.routes import tasks, auth
import os

app = FastAPI(title="Reminder Bot API")

# CORS для веб-додатку
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшені вкажіть конкретний домен
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Підключення до існуючих компонентів
from core.database import DatabaseManager
from core.scheduler import ReminderManager

db = DatabaseManager()
reminder_manager = ReminderManager(db)

# Ініціалізація (викликається при старті)
@app.on_event("startup")
async def startup():
    await db.init_database()
    reminder_manager.set_application(None)  # Буде встановлено пізніше
    reminder_manager.start()
    
    # Відновлення завдань
    async with db._get_connection() as conn:
        cursor = await conn.execute('SELECT * FROM tasks WHERE is_completed = 0')
        rows = await cursor.fetchall()
        tasks = [db._row_to_task(row) for row in rows]
        for task in tasks:
            reminder_manager.schedule_task(task)

# Залежності
def get_db():
    return db

def get_reminder_manager():
    return reminder_manager

# Підключення роутів
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

## 2. API Routes (api/routes/tasks.py)

```python
from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional
from api.models.schemas import TaskCreate, TaskUpdate, TaskResponse
from api.utils.telegram_auth import validate_init_data, get_user_id
from core.database import DatabaseManager
from core.scheduler import ReminderManager

router = APIRouter()

async def get_current_user(
    x_telegram_init_data: Optional[str] = Header(None),
    db: DatabaseManager = Depends(lambda: get_db())
):
    """Витягує user_id з Telegram initData"""
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="Missing initData")
    
    try:
        init_data = validate_init_data(
            x_telegram_init_data,
            os.getenv("TELEGRAM_BOT_TOKEN")
        )
        user_id = get_user_id(init_data)
        return user_id
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid initData")

@router.get("", response_model=list[TaskResponse])
async def get_tasks(
    user_id: int = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db)
):
    """Отримати всі нагадування користувача"""
    tasks = await db.get_user_tasks(user_id)
    return tasks

@router.post("", response_model=TaskResponse)
async def create_task(
    task: TaskCreate,
    user_id: int = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db),
    reminder_manager: ReminderManager = Depends(get_reminder_manager)
):
    """Створити нове нагадування"""
    task_id = await db.add_task(
        user_id=user_id,
        description=task.description,
        days=task.days,
        times=task.times,
        interval_minutes=task.interval_minutes,
        is_one_time=task.is_one_time,
        one_time_date=task.one_time_date
    )
    
    created_task = await db.get_task(task_id)
    if created_task:
        reminder_manager.schedule_task(created_task)
    
    return created_task

@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    task: TaskUpdate,
    user_id: int = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db),
    reminder_manager: ReminderManager = Depends(get_reminder_manager)
):
    """Оновити нагадування"""
    existing_task = await db.get_task(task_id)
    if not existing_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if existing_task['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    updates = task.dict(exclude_unset=True)
    await db.update_task(task_id, **updates)
    
    updated_task = await db.get_task(task_id)
    reminder_manager.cancel_task(user_id, task_id)
    reminder_manager.schedule_task(updated_task)
    
    return updated_task

@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    user_id: int = Depends(get_current_user),
    db: DatabaseManager = Depends(get_db),
    reminder_manager: ReminderManager = Depends(get_reminder_manager)
):
    """Видалити нагадування"""
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    reminder_manager.cancel_task(user_id, task_id)
    await db.delete_task(task_id)
    
    return {"message": "Task deleted"}
```

## 3. Pydantic моделі (api/models/schemas.py)

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class TaskBase(BaseModel):
    description: str = Field(..., min_length=1, max_length=500)
    days: List[int] = Field(default_factory=list)
    times: List[str] = Field(..., min_items=1)
    interval_minutes: int = Field(..., ge=1, le=1440)
    is_one_time: bool = False
    one_time_date: Optional[str] = None

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    description: Optional[str] = None
    days: Optional[List[int]] = None
    times: Optional[List[str]] = None
    interval_minutes: Optional[int] = None
    is_one_time: Optional[bool] = None
    one_time_date: Optional[str] = None

class TaskResponse(TaskBase):
    task_id: int
    user_id: int
    is_completed: bool
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
```

## 4. Валідація Telegram (api/utils/telegram_auth.py)

```python
import hashlib
import hmac
import json
from urllib.parse import parse_qsl
import os

def validate_init_data(init_data: str, bot_token: str) -> dict:
    """Валідує Telegram Web App initData"""
    parsed_data = dict(parse_qsl(init_data))
    hash_value = parsed_data.pop('hash', '')
    
    data_check_string = '\n'.join(
        f"{k}={v}" for k, v in sorted(parsed_data.items())
    )
    
    secret_key = hmac.new(
        "WebAppData".encode(),
        bot_token.encode(),
        hashlib.sha256
    ).digest()
    
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()
    
    if calculated_hash != hash_value:
        raise ValueError("Invalid initData signature")
    
    return parsed_data

def get_user_id(init_data: dict) -> int:
    """Витягує user_id з валідованого initData"""
    user_str = init_data.get('user')
    if not user_str:
        raise ValueError("User data not found")
    
    user_data = json.loads(user_str)
    return int(user_data['id'])
```

## 5. Базовий веб-додаток (webapp/index.html)

```html
<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Нагадування</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <div class="container">
        <header>
            <h1>📋 Мої нагадування</h1>
            <button id="addTaskBtn" class="btn-primary">➕ Додати</button>
        </header>
        
        <div id="taskList" class="task-list"></div>
        
        <div id="taskForm" class="task-form hidden">
            <h2 id="formTitle">Створити нагадування</h2>
            <form id="taskFormElement">
                <input type="text" id="description" placeholder="Опис завдання" required>
                
                <div class="form-group">
                    <label>Тип:</label>
                    <select id="taskType">
                        <option value="recurring">Повторюване</option>
                        <option value="one-time">Одноразове</option>
                    </select>
                </div>
                
                <div id="daysSelector" class="form-group">
                    <label>Дні тижня:</label>
                    <div class="day-buttons">
                        <button type="button" class="day-btn" data-day="0">Пн</button>
                        <button type="button" class="day-btn" data-day="1">Вт</button>
                        <button type="button" class="day-btn" data-day="2">Ср</button>
                        <button type="button" class="day-btn" data-day="3">Чт</button>
                        <button type="button" class="day-btn" data-day="4">Пт</button>
                        <button type="button" class="day-btn" data-day="5">Сб</button>
                        <button type="button" class="day-btn" data-day="6">Нд</button>
                    </div>
                </div>
                
                <div id="dateSelector" class="form-group hidden">
                    <label>Дата:</label>
                    <input type="date" id="oneTimeDate">
                </div>
                
                <div class="form-group">
                    <label>Час (через кому):</label>
                    <input type="text" id="times" placeholder="09:00, 18:00" required>
                </div>
                
                <div class="form-group">
                    <label>Інтервал повторення (хвилин):</label>
                    <input type="number" id="interval" value="30" min="1" max="1440" required>
                </div>
                
                <div class="form-actions">
                    <button type="submit" class="btn-primary">Зберегти</button>
                    <button type="button" id="cancelBtn" class="btn-secondary">Скасувати</button>
                </div>
            </form>
        </div>
    </div>
    
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="app.js"></script>
</body>
</html>
```

## 6. JavaScript логіка (webapp/app.js)

```javascript
// Ініціалізація Telegram Web App
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

// Отримання даних користувача
const initData = tg.initData;
const API_URL = 'https://your-api-domain.com/api'; // Замініть на ваш URL

// API функції
async function apiRequest(endpoint, options = {}) {
    const response = await fetch(`${API_URL}${endpoint}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            'X-Telegram-Init-Data': initData,
            ...options.headers
        }
    });
    
    if (!response.ok) {
        throw new Error(`API error: ${response.statusText}`);
    }
    
    return response.json();
}

// Завантаження нагадувань
async function loadTasks() {
    try {
        const data = await apiRequest('/tasks');
        renderTasks(data.tasks || data);
    } catch (error) {
        console.error('Error loading tasks:', error);
        tg.showAlert('Помилка завантаження нагадувань');
    }
}

// Відображення нагадувань
function renderTasks(tasks) {
    const taskList = document.getElementById('taskList');
    
    if (tasks.length === 0) {
        taskList.innerHTML = '<p class="empty">Немає нагадувань</p>';
        return;
    }
    
    taskList.innerHTML = tasks.map(task => `
        <div class="task-card">
            <h3>${task.description}</h3>
            <p>Часи: ${task.times.join(', ')}</p>
            <p>Інтервал: ${task.interval_minutes} хв</p>
            <div class="task-actions">
                <button onclick="editTask(${task.task_id})">✏️ Редагувати</button>
                <button onclick="deleteTask(${task.task_id})">🗑 Видалити</button>
            </div>
        </div>
    `).join('');
}

// Створення нагадування
async function createTask(taskData) {
    try {
        await apiRequest('/tasks', {
            method: 'POST',
            body: JSON.stringify(taskData)
        });
        tg.showAlert('Нагадування створено!');
        loadTasks();
        hideForm();
    } catch (error) {
        tg.showAlert('Помилка створення нагадування');
    }
}

// Видалення нагадування
async function deleteTask(taskId) {
    if (!confirm('Видалити нагадування?')) return;
    
    try {
        await apiRequest(`/tasks/${taskId}`, { method: 'DELETE' });
        tg.showAlert('Нагадування видалено!');
        loadTasks();
    } catch (error) {
        tg.showAlert('Помилка видалення');
    }
}

// Обробка форми
document.getElementById('taskFormElement').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const taskType = document.getElementById('taskType').value;
    const taskData = {
        description: document.getElementById('description').value,
        times: document.getElementById('times').value.split(',').map(t => t.trim()),
        interval_minutes: parseInt(document.getElementById('interval').value),
        is_one_time: taskType === 'one-time',
        days: [],
        one_time_date: null
    };
    
    if (taskType === 'recurring') {
        const selectedDays = Array.from(document.querySelectorAll('.day-btn.selected'))
            .map(btn => parseInt(btn.dataset.day));
        taskData.days = selectedDays;
    } else {
        const date = document.getElementById('oneTimeDate').value;
        taskData.one_time_date = date;
    }
    
    await createTask(taskData);
});

// Завантаження при старті
loadTasks();
```

## 7. Оновлення bot/keyboards.py

```python
from telegram import ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

# Додати кнопку з WebApp
WEBAPP_URL = "https://your-domain.com/webapp"  # Замініть на ваш URL

def get_main_keyboard_with_webapp():
    """Головна клавіатура з кнопкою WebApp"""
    keyboard = [
        ['➕ Створити нагадування'],
        ['📋 Мої нагадування'],
        ['🗑 Видалити нагадування']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_webapp_button():
    """Кнопка для відкриття Mini App"""
    return InlineKeyboardButton(
        "📱 Відкрити додаток",
        web_app=WebAppInfo(url=WEBAPP_URL)
    )
```

## 8. Оновлення bot/handlers.py

```python
# Додати в метод start:
async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    if not user or not update.message:
        return
    
    # Додати кнопку з WebApp
    webapp_button = get_webapp_button()
    keyboard = InlineKeyboardMarkup([[webapp_button]])
    
    await update.message.reply_text(
        f"Привіт, {user.first_name}! 👋\n\n"
        "Я твій особистий бот-нагадувач.\n\n"
        "Натисни кнопку нижче, щоб відкрити додаток:",
        reply_markup=keyboard
    )
```

## 9. Запуск

```bash
# Термінал 1: Запуск бота
python main.py

# Термінал 2: Запуск API
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Термінал 3: Запуск веб-додатку (якщо локально)
# Або задеплоїти на Vercel/Netlify
```

## 10. Оновлений requirements.txt

```
python-telegram-bot==21.3
APScheduler==3.11.0
python-dotenv==1.0.0
schedule==1.2.2
aiosqlite==0.19.0
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0
```

---

**Примітка**: Це базові приклади. Потрібно додати обробку помилок, валідацію, покращений UI та інші деталі.

