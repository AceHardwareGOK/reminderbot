import logging
import os
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, filters, ConversationHandler
)

import asyncio
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import uvicorn
from telegram import MenuButtonWebApp, WebAppInfo
from core.config import LOG_LEVEL, WEBAPP_PORT, WEBAPP_URL
from core.database import DatabaseManager
from core.scheduler import ReminderManager
from bot.handlers import BotHandlers
from bot.states import ConversationState
from bot.edit_handlers import EditHandlers
from api.routes import router as api_router, set_reminder_manager

# FastAPI App for Telegram Web App
fastapi_app = FastAPI(title="ReminderBot Web App API")

@fastapi_app.middleware("http")
async def add_tunnel_bypass_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Bypass-Tunnel-Reminder"] = "true"
    response.headers["Ngrok-Skip-Browser-Warning"] = "true"
    if request.url.path.startswith("/web"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

fastapi_app.include_router(api_router)


# Mount web static files
if os.path.exists("web"):
    fastapi_app.mount("/web", StaticFiles(directory="web", html=True), name="web")

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)

def main():
    """Start the bot"""
    # Initialize objects (sync)
    db = DatabaseManager()
    reminder_manager = ReminderManager(db)
    set_reminder_manager(reminder_manager)

    handlers = BotHandlers(db, reminder_manager)
    edit_handlers = EditHandlers(db, reminder_manager, handlers.validator)
    
    # Initialize bot application
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        return

    async def post_init(app: Application):
        """Async initialization tasks"""
        logger.info("Running post_init...")
        
        # Initialize database
        await db.init_database()
        
        # Link application to reminder manager
        reminder_manager.set_application(app)
        
        # Start scheduler (it will attach to the current event loop)
        reminder_manager.start()
        
        # Restore scheduled tasks
        try:
            async with db._get_connection() as conn:
                cursor = await conn.execute('SELECT * FROM tasks WHERE is_completed = 0')
                rows = await cursor.fetchall()
                tasks = [db._row_to_task(row) for row in rows]
                
                count = 0
                for task in tasks:
                    reminder_manager.schedule_task(task)
                    count += 1
                logger.info(f"Restored {count} tasks from database")
        except Exception as e:
            logger.error(f"Error restoring tasks: {e}")

        # Configure Telegram Menu Button for Web App if URL provided
        webapp_url = os.getenv("WEBAPP_URL") or WEBAPP_URL
        if webapp_url:
            try:
                await app.bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(text="📋 Нагадування", web_app=WebAppInfo(url=webapp_url))
                )
                logger.info(f"Telegram Chat Menu Button set to Web App URL: {webapp_url}")
            except Exception as e:
                logger.error(f"Error setting Telegram Chat Menu Button: {e}")


        # Start FastAPI Web Server in the same asyncio event loop
        config = uvicorn.Config(app=fastapi_app, host="0.0.0.0", port=WEBAPP_PORT, log_level="warning")
        server = uvicorn.Server(config)
        asyncio.create_task(server.serve())
        logger.info(f"FastAPI Web App server listening on http://0.0.0.0:{WEBAPP_PORT}")



    # Build application with post_init
    application = Application.builder().token(token).post_init(post_init).build()

    
    # Setup edit conversation handler
    edit_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_handlers.edit_reminder_start, pattern=r'^edit_\d+$')],
        states={
            ConversationState.EDIT_SELECT_FIELD.value: [
                CallbackQueryHandler(edit_handlers.edit_select_field, pattern='^edit')
            ],
            ConversationState.EDIT_ENTER_VALUE.value: [
                CallbackQueryHandler(edit_handlers.edit_callback_value, pattern='^edit'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_handlers.edit_enter_value)
            ],
            ConversationState.EDIT_CHOOSING_DAYS.value: [
                CallbackQueryHandler(edit_handlers.edit_callback_value, pattern='^edit'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_handlers.edit_choosing_days)
            ],
            ConversationState.EDIT_CHOOSING_ONE_TIME_DATE.value: [
                CallbackQueryHandler(edit_handlers.edit_callback_value, pattern='^edit'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_handlers.edit_choosing_one_time_date)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(edit_handlers.edit_select_field, pattern='^edit_cancel$'),
            MessageHandler(filters.Regex('^🏠 Скасувати$'), handlers.cancel)
        ]
    )

    # Setup create conversation handler
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex('^➕ Створити нагадування$'), handlers.create_reminder_start),
            CommandHandler('create', handlers.create_reminder_start)
        ],
        states={
            ConversationState.DESCRIBING_TASK.value: [
                CallbackQueryHandler(handlers.handle_wizard_callback, pattern='^wiz'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_description)
            ],
            ConversationState.CHOOSING_DAYS.value: [
                CallbackQueryHandler(handlers.handle_wizard_callback, pattern='^wiz'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_days)
            ],
            ConversationState.CHOOSING_TIMES.value: [
                CallbackQueryHandler(handlers.handle_wizard_callback, pattern='^wiz'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_times)
            ],
            ConversationState.CHOOSING_INTERVAL.value: [
                CallbackQueryHandler(handlers.handle_wizard_callback, pattern='^wiz'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_interval)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(handlers.handle_wizard_callback, pattern='^wiz_cancel$'),
            MessageHandler(filters.Regex('^🏠 Скасувати$'), handlers.cancel),
            CommandHandler('cancel', handlers.cancel)
        ]
    )
    
    # Register handlers
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("debug_time", handlers.debug_time))
    application.add_handler(CommandHandler("refresh", handlers.refresh_scheduler))
    application.add_handler(MessageHandler(filters.Regex('^📋 Мої нагадування$'), handlers.view_reminders))

    # Global handler for snooze text input.
    # Placed in a lower-priority group so it doesn't block
    # the main conversation handlers (create/edit flows).
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handlers.handle_snooze_text,
        ),
        group=1,
    )
    
    # Register edit handler BEFORE generic button handler
    application.add_handler(edit_conv_handler)
    
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(handlers.button_handler))

    
    # Start bot (run_polling manages the event loop)
    logger.info("Starting bot polling...")
    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
