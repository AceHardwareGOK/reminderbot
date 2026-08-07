# ReminderBot — Повний Контекст Проєкту

## 📋 Опис проєкту
Telegram-бот для гнучкого управління нагадуваннями з підтримкою кількох часів на день, конкретних дат, відкладення (Snooze), редагування та дашбордом завдань. Інтерфейс побудований за стандартами Telegram Rich MarkdownV2 з одноповідомленням-майстром (Single-Message Wizard) та кольоровими Inline-кнопками.

## 🛠️ Технологічний стек
- **Мова**: Python 3.12+
- **Фреймворк бота**: `python-telegram-bot` (v20+ Async)
- **REST API & Web App Backend**: `FastAPI` + `uvicorn`
- **Frontend Mini App**: HTML5, CSS3 (Telegram theme variables), Vanilla JS (Telegram WebApp SDK `telegram-web-app.js`)
- **Планувальник**: `APScheduler` (`AsyncIOScheduler`)
- **База даних**: `SQLite` через `aiosqlite`
- **Часовий пояс**: `Europe/Kyiv` (`zoneinfo`)
- **Хостинг & CI/CD**: AWS EC2 (`t3.micro`, регіон `eu-north-1`) + GitHub Actions (`.github/workflows/deploy.yml`)
- **Граф знань**: `graphify` (`graphify-out/`)
- **Стиснення виводу**: `rtk` (Reduced Token Kit)

## 📌 Поточний стан
- Працюємо у гілці `feature/telegram-webapp`.
- **Реалізовано концепт Telegram Web App (Mini App)**:
  - Додано `FastAPI` REST API (`api/routes.py`), що працює в тому ж `asyncio` event loop бота (`main.py`).
  - Реалізовано перевірку автентичності `initData` Telegram за HMAC-SHA256 (`api/auth.py`).
  - Створено Vanilla JS SPA фронтенд у папочці `web/` (`index.html`, `app.css`, `app.js`) з підтримкою темних/світлих тем Telegram, вкладок (Список завдань, Календар, Форма створення).
  - У `bot/keyboards.py` додано кнопку `📱 Відкрити Web App`.
  - Чат-інтерфейс бота повністю збережено (сповіщення, inline-кнопки, дашборд та майстри в чаті працюють паралельно без змін).

## 📁 Структура та файли проєкту
- [`main.py`](file:///d:/sites/reminderbot/main.py) — Точка входу, ініціалізація бота, реєстрація handlers, інтеграція FastAPI веб-сервера у post_init.
- [`api/auth.py`](file:///d:/sites/reminderbot/api/auth.py) — Перевірка підпису Telegram WebApp `initData` (HMAC-SHA256).
- [`api/routes.py`](file:///d:/sites/reminderbot/api/routes.py) — REST API ендпоінти (`GET/POST/PUT/DELETE /api/tasks`, `/api/tasks/{id}/complete`).
- [`web/index.html`](file:///d:/sites/reminderbot/web/index.html) — HTML5 макет Telegram Mini App.
- [`web/app.css`](file:///d:/sites/reminderbot/web/app.css) — Стилі Mini App з Telegram темами.
- [`web/app.js`](file:///d:/sites/reminderbot/web/app.js) — JS логіка Web App (Telegram SDK, AJAX запити, Календар).
- [`bot/handlers.py`](file:///d:/sites/reminderbot/bot/handlers.py) — Обробка майстра створення (Кроки 1-4), кнопки дашборду (`dashdone`, `dashsnooze`, `snoozeall`), обробка відкладення.
- [`bot/edit_handlers.py`](file:///d:/sites/reminderbot/bot/edit_handlers.py) — Меню редагування завдань з Rich MarkdownV2 картками, інтерактивними InlineKeyboards та авто-очищенням чату.
- [`bot/ui_helpers.py`](file:///d:/sites/reminderbot/bot/ui_helpers.py) — Генератор Telegram Rich MarkdownV2 карт.
- [`bot/keyboards.py`](file:///d:/sites/reminderbot/bot/keyboards.py) — Головні меню та клавіатури дашборду + Web App кнопка.
- [`bot/states.py`](file:///d:/sites/reminderbot/bot/states.py) — Стан для `ConversationHandler`.
- [`core/scheduler.py`](file:///d:/sites/reminderbot/core/scheduler.py) — `ReminderManager`, інтеграція з APScheduler.
- [`core/database.py`](file:///d:/sites/reminderbot/core/database.py) — `DatabaseManager`, створення таблиць, CRUD операції.
- [`core/config.py`](file:///d:/sites/reminderbot/core/config.py) — Завантаження конфігурації `.env` / `WEBAPP_URL` / `WEBAPP_PORT`.
- [`utils/validators.py`](file:///d:/sites/reminderbot/utils/validators.py) — Валідація та парсинг часу, інтервалів, дат.
- [`.github/workflows/deploy.yml`](file:///d:/sites/reminderbot/.github/workflows/deploy.yml) — Автоматичний CI/CD деплой на AWS EC2 при пуші в `main`.

## ⚡ MCP та Скіли в проєкті
- **`context7`**: Документація та вирішення бібліотек/API.
- **`graphify`**: Автоматична підтримка графа знань коду (`rtk graphify update .`).
- **`git-pushing`**: Конвенційні комміти та автоматизований git push workflow.
- **`rtk`**: Обов'язкове використання для виконання термінальних команд (`rtk git status`, `rtk pytest`, `rtk python -m py_compile`).

## 📝 Що зроблено та працює
1. **Повне перенесення функціоналу бота в Telegram Web App (Mini App)**:
   - **Графічні елементи (Time & Date Pickers)**: додано вибір часу через Time Picker + швидкі пресет-чіпи (`08:00`, `09:00`, `12:00`, `18:00`) з формуванням кольорових тегів `[09:00 ❌]`, вибір дати через Date Picker з пресетами (`Сьогодні`, `Завтра`, `+3 дні`), та чіпи інтервалу (`Без повтору`, `15 хв`, `30 хв`, `1 год`).
   - **Створення нагадувань**: модалка з графічними контролерами.
   - **Синхронізація часового поясу (Europe/Kyiv)**: виправлено UTC-зсув на 3 години у `utils/validators.py` (використання `ZoneInfo("Europe/Kyiv")`) та у `web/app.js` (перехід на `getLocalDateISO()` замість `toISOString()`).
   - **Перегляд & Фільтрація**: картки з прогрес-баром виконання за день, фільтри "Всі", "Сьогодні", "Щоденні", "Одноразові".
   - **Виправлено відображення на вкладці "Сьогодні"**: оновлено `renderTaskList()` у `web/app.js` для використання універсальної функції `isTaskOnDate(t, todayDate, todayIndex)`, що забезпечило відображення як щоденних/повторюваних нагадувань, так і одноразових завдань, призначених на сьогодні. На бекенді (`api/routes.py`) також виправлено розпарсинг дат для точного підрахунку `today_active_count`.
   - **Усунуто застарілий кеш Telegram WebView**: додано middleware з No-Cache заголовками (`Cache-Control: no-cache, no-store, must-revalidate`) у `main.py`, а також версіонування у `web/index.html` (`app.js?v=1.0.2`, `app.css?v=1.0.2`) та виправлено id елемента підрахунку активних завдань у профілі (`stats-subtitle`).
   - **Редагування**: модальне вікно з графічним редагуванням часів, інтервалу та днів тижня.
   - **Відкладення (Snooze & Snooze All)**: відкладення конкретного завдання чи всіх завдань на 15/30/60/120 хвилин та скидання відкладення.
   - **Точний прогрес виконання на сьогодні**: бекенд обчислює відсоток виконання `completed_today_count / total_today_count * 100%` з урахуванням локального часового поясу (`Europe/Kyiv`) незалежно від нічного часу (між 00:00 та 03:00).
   - **Календар**: підсвітка днів у календарі підтримує і повторювані, і одноразові завдання, а сьогоднішній день виділяється за замовчуванням при відкритті.
   - **Анімації та свайпи в календарі**: додано обробку сенсорних та вказівникових свайпів вліво/вправо (`touchstart`/`touchend` та `pointerdown`/`pointerup`) безпосередньо на картку `.calendar-card` з CSS `touch-action: pan-y` для бездоганного перемикання місяців на будь-яких пристроях.

     - **Візуалізація та точне по-слотове відмічання часів нагадувань**: додано обчислення актуальних статусів слотів часу на бекенді (`completed` ✅, `next` ⏳, `upcoming` 🕒, `past` ⚠️) та їх відображення у вигляді інтерактивних пульсуючих чіпів `.time-slot-chip` у Web App і статус-маркерів у чат-картках бота. Виправлено кнопку "✅ Готово": тепер вона відмічає **тільки один актуальний слот часу**, а не всі часи нагадування відразу.
     - **Окреме компонування кнопок дій у WebApp та чаті бота**: у WebApp 4 кнопки дій картки розміщено в одну лінію `repeat(4, 1fr)`, а у чаті Telegram (`build_dashboard_keyboard` у `bot/keyboards.py`) кнопки розбито на 2 ряди (Рядок 1: `✅ Готово`, `✏️ Редагувати`; Рядок 2: `⏸ Відкласти`, `🗑 Видалити`) з повними незрізаними підписами.
     - **Захист від 502 Bad Gateway при видаленні**: додано ендпоінт `POST /api/tasks/{task_id}/delete` у `api/routes.py` для обходу блокувань HTTP DELETE методів у localtunnel/проксі.
     - **Світла тема та перемикач тем (Theme Engine)**: додано кнопку `#theme-toggle-btn` 🌙/☀️ у шапку WebApp з анімацією натискання. Реалізовано збереження обраного режиму у `localStorage` (`app_theme`), автовизначення системного/телеграмного режиму (`tg.colorScheme`, `prefers-color-scheme`), а також слухач `themeChanged` Telegram SDK. Для `[data-theme="light"]` розроблено елегантну колірну палітру з м'якими тінями, підлаштованими інпутами, картками та чіпами слотів часів.
      - **Повне дотримання вимог Accessibility (WCAG 2.2 AA) та виразне підсвічування вкладок**: додано `aria-label` для всіх іконкових кнопок, контур фокусу `:focus-visible`. Створено капсульний Pill-фон `rgba(82, 136, 193, 0.18)`, верхній індикатор-лінію `::before`, масштабування іконки `scale(1.22)` та жирний шрифт `font-weight: 700` для активної вкладки у Bottom Navigation Bar.
      - **Один UI-патерн для вибору часу та інтервалів**: блок вибору повторів приведено до аналогічної логіки вибору часу — інпут кількості хвилин (`#task-interval-input`, `#edit-task-interval-input`) та рядок швидких чіпів-пресетів (`Без повтору`, `15 хв`, `30 хв`, `1 год`, `2 год`). Працює двостороння інтерактивна синхронізація.
      - **100% контрастність у Світлій Темі (Light Theme Fix)**: виправлено колір тексту для всіх чіпів фільтрів (`.notif-filter-chip`) та чіпів-пресетів у світлій темі. Забезпечено виразний темний шрифт `#1e293b` на білих і слабко-блакитних капсулах та контрастні білі написи на активній кнопці `#2b73d2`.
      - **Фільтр "Сьогодні" за замовчуванням**: у списку завдань (`currentFilter = 'today'`) та вкладці сповіщень (`currentNotifFilter = 'today'`) за замовчуванням активовано фільтр на сьогоднішній день.
      - **Повне опрацювання рекомендацій /better-interface**: інтерактивні кнопки видалення тегів часу отримали нативні семантичні елементи `<button type="button">` з `aria-label="Видалити час HH:MM"`, всі чіпи пресетів — атрибути `aria-pressed="true/false"`, додано `tabular-nums` для цифр часів `HH:MM` та плавну безшумну прокрутку чіп-барів.
      - **Multi-Date Picker у WebApp (декілька дат для одноразових нагадувань)**: у модальні вікна створення та редагування впроваджено функціонал додавання декількох дат (кнопка `➕ Додати дату`, `preset-chips` та контейнери тегів обраних дат `#selected-dates-container`, `#edit-selected-dates-container`). Повернуто виразні червоні хрестики `❌` без системного сірого фону кнопки.
       - **Захист від дублювання часів та дат (Duplicate Protection)**: додано валідацію додавання та змінення часів/дат. При спробі додати повторний час чи дату у модалках створення та редагування видається попередження `⚠️ Цей час вже є у списку!` або `⚠️ Цю дату вже додано!`, що запобігає зацикленню та дублюванню.
       - **Вибір дати "Сьогодні" за замовчуванням**: реалізовано аналогічно логіці вибору часу — за замовчуванням для дати автоматично вибирається поточний день (`getLocalDateISO()`), підсвічується активний тег `📅 YYYY-MM-DD ❌`, а пресет-чіпи дат ("Сьогодні", "Завтра", "+3 дні") відображають активний стан та підтримують перемикання/додавання. Версію статики піднято до `v=1.0.22`.
       - **Реальний динамічний повтор нагадувань ("🔁 Повторити")**: у `ReminderManager` додано метод `schedule_snooze_reminder`, який планить одноразовий `DateTrigger` в APScheduler на `now + N хв`. Назва кнопки адаптується: до спрацювання — `⏸ Відкласти`, а після спрацювання нагадування / у сповіщеннях — `🔁 Повторити`. Працює ідентично та синхронно у боті та WebApp.



2. **Паралельна робота чату бота**:
   - Чат-майстер створення, меню редагування, сповіщення, inline-кнопки `✅ Готово` та `⏸ Відкласти` у чаті залишаються 100% робочими та ділять єдину SQLite БД і `ReminderManager`.
   - Виправлено виклик `cancel_repeat_tasks` та надійне маркування екземплярів виконання з кнопки чату.
   - Усунено `NameError: name 'reminder_instance_id' is not defined` в `_handle_done`.
   - Виправлено `has_remaining_one_time_slots` для одноразових завдань з одним часом: після відмітки готово завдання негайно знімається з розкладу та видаляється з бази.






## 🚀 Поточний стан деплою на AWS EC2
- **Повна реалізація у гілці `main`**: код об'єднано з `feature/telegram-webapp` і успішно відправлено в `origin/main`.
- **Автоматизований деплой на EC2**: GitHub Actions (`.github/workflows/deploy.yml`) автоматично деплоїть при пуші в `main`.
- **Стабільний HTTPS через DuckDNS + nginx + Let's Encrypt**:
  - Домен: `irkasreminder.duckdns.org` → EC2 IP `16.170.238.45`
  - nginx reverse proxy: порт 443 (HTTPS) → localhost:8080 (FastAPI)
  - SSL сертифікат Let's Encrypt з авто-оновленням (certbot, дійсний до 2026-11-05)
  - `WEBAPP_URL=https://irkasreminder.duckdns.org/web` у `.env` на EC2
  - EC2 Security Group `sg-0ed82973098ff71f1`: відкриті порти 22, 80, 443
  - Cloudflare Quick Tunnel видалено (був нестабільний, змінював URL при рестарті)
- **Доведено до ідеалу логіку вибору часів у WebApp (activeTimeIndex)**:
  - Колесо часу `timePicker` прив'язано до активного слоту (`activeTimeIndex`), який яскраво підсвічується рамкою `.active-tag`.
  - Обертання колеса часу редагує **виключно активний тег**, не створюючи нових тегів при виборі.
  - Кнопка `➕ Додати час` ЯВНО створює новий додатковий слот часу, робить його активним та виставляє колесо на новий час.
  - Тап на будь-який з існуючих тегів часу в списку перемикає активний слот для колеса.
  - Піднято версію `app.js` у `index.html` до `v=1.0.4`.
- **Виправлено критичний баг з завантаженням даних у WebApp**:
  - Функція `loadTasks()` була відсутня у `web/app.js` — викликалась 8 разів, але ніде не була визначена.
  - Додано `async function loadTasks()`: GET `/api/tasks`, оновлення `tasks[]`, прогрес-бару та лічильника, виклик `renderTaskList()`.

## 🔧 Інфраструктура EC2 (сервіси)
| Сервіс | systemd unit | Статус |
|--------|-------------|--------|
| Telegram Bot + FastAPI | `reminderbot.service` | ✅ enabled |
| nginx (reverse proxy) | `nginx.service` | ✅ enabled |
| certbot (auto-renew) | `certbot.timer` | ✅ auto |
| cloudflared-tunnel | `cloudflared-tunnel.service` | ❌ disabled (видалено) |









