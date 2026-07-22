# Graph Report - reminderbot  (2026-07-22)

## Corpus Check
- 13 files · ~8,982 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 229 nodes · 495 edges · 10 communities (9 shown, 1 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 52 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d8931562`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]

## God Nodes (most connected - your core abstractions)
1. `DatabaseManager` - 39 edges
2. `BotHandlers` - 35 edges
3. `ReminderManager` - 27 edges
4. `DEFAULT_TYPE` - 26 edges
5. `DayOfWeek` - 23 edges
6. `Update` - 22 edges
7. `ConversationState` - 16 edges
8. `Validator` - 15 edges
9. `EditHandlers` - 14 edges
10. `str` - 13 edges

## Surprising Connections (you probably didn't know these)
- `bool` --uses--> `DayOfWeek`  [INFERRED]
  bot/ui_helpers.py → core/scheduler.py
- `EditHandlers` --uses--> `DayOfWeek`  [INFERRED]
  bot/edit_handlers.py → core/scheduler.py
- `Update` --uses--> `DayOfWeek`  [INFERRED]
  bot/edit_handlers.py → core/scheduler.py
- `DEFAULT_TYPE` --uses--> `DayOfWeek`  [INFERRED]
  bot/edit_handlers.py → core/scheduler.py
- `BotHandlers` --uses--> `DatabaseManager`  [INFERRED]
  bot/handlers.py → core/database.py

## Communities (10 total, 1 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (25): BotHandlers, DEFAULT_TYPE, Update, Start Single-Message Wizard for reminder creation, Get task description and advance Single-Message Wizard to step 2, Fallback for text input in days step, Handle custom text input for times (e.g., 09:30, 18:00) in wizard, Handle custom text input for interval (e.g., 45, 90, 1:30) in wizard (+17 more)

### Community 1 - "Community 1"
Cohesion: 0.10
Nodes (21): DatabaseManager, bool, int, str, Async database manager using aiosqlite, Get all tasks for a user, Mark a specific reminder instance as completed, Check if a reminder instance is completed (+13 more)

### Community 2 - "Community 2"
Cohesion: 0.08
Nodes (21): Application, bool, DatabaseManager, int, str, Set the Telegram application instance, Schedule all reminders for a task, Check if a task still has scheduled future jobs in the scheduler. (+13 more)

### Community 3 - "Community 3"
Cohesion: 0.11
Nodes (18): DatabaseManager, int, str, Handle choice of snooze duration for a single reminder., Persist snooze for a single reminder instance., DayOfWeek, Days of the week mapping, Get day from short name (+10 more)

### Community 4 - "Community 4"
Cohesion: 0.17
Nodes (22): build_wiz_days_keyboard(), build_wiz_interval_keyboard(), build_wiz_times_keyboard(), escape_md(), format_progress_header(), format_reminder_notification(), format_task_card(), format_wizard_step() (+14 more)

### Community 5 - "Community 5"
Cohesion: 0.16
Nodes (12): EditHandlers, DEFAULT_TYPE, Update, Handle new value input, Handlers for editing reminders, Handle day selection in edit mode, Start edit flow from callback, Handle one-time date selection in edit mode (+4 more)

### Community 6 - "Community 6"
Cohesion: 0.18
Nodes (10): code:bash (git clone git@github.com:AceHardwareGOK/reminderbot.git), code:bash (python -m venv .venv), code:bash (pip install -r requirements.txt), code:env (TELEGRAM_BOT_TOKEN=ваш_токен_від_BotFather), code:bash (python main.py), Reminder Bot 🤖, 🚀 Встановлення та запуск, 🌟 Основні можливості (+2 more)

### Community 7 - "Community 7"
Cohesion: 0.32
Nodes (7): build_dashboard_keyboard(), build_reminder_keyboard(), InlineKeyboardMarkup, int, str, Build interactive dashboard keyboard with pagination and action buttons., Build reminder notification keyboard with styled buttons.

### Community 8 - "Community 8"
Cohesion: 0.33
Nodes (5): ReminderBot — Контекст проєкту, Наступні кроки, Опис проєкту, Поточний стан, Що зроблено (Останні зміни)

## Knowledge Gaps
- **15 isolated node(s):** `str`, `Row`, `Опис проєкту`, `Поточний стан`, `Що зроблено (Останні зміни)` (+10 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `DatabaseManager` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 4`?**
  _High betweenness centrality (0.292) - this node is a cross-community bridge._
- **Why does `ReminderManager` connect `Community 2` to `Community 0`, `Community 1`, `Community 3`, `Community 4`?**
  _High betweenness centrality (0.180) - this node is a cross-community bridge._
- **Why does `BotHandlers` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 5`?**
  _High betweenness centrality (0.155) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `DatabaseManager` (e.g. with `Application` and `BotHandlers`) actually correct?**
  _`DatabaseManager` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `BotHandlers` (e.g. with `ConversationState` and `DatabaseManager`) actually correct?**
  _`BotHandlers` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `ReminderManager` (e.g. with `BotHandlers` and `DatabaseManager`) actually correct?**
  _`ReminderManager` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `DEFAULT_TYPE` (e.g. with `ConversationState` and `DatabaseManager`) actually correct?**
  _`DEFAULT_TYPE` has 5 INFERRED edges - model-reasoned connections that need verification._