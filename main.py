import logging
import os
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, filters, ConversationHandler
)

from core.config import LOG_LEVEL
from core.database import DatabaseManager
from core.scheduler import ReminderManager
from bot.handlers import BotHandlers
from bot.states import ConversationState
from bot.edit_handlers import EditHandlers

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

    # Build application with post_init
    application = Application.builder().token(token).post_init(post_init).build()
    
    # Setup edit conversation handler
    edit_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_handlers.edit_reminder_start, pattern='^edit_\d+$')],
        states={
            ConversationState.EDIT_SELECT_FIELD.value: [
                CallbackQueryHandler(edit_handlers.edit_select_field, pattern='^edit_')
            ],
            ConversationState.EDIT_ENTER_VALUE.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_handlers.edit_enter_value)
            ],
            ConversationState.EDIT_CHOOSING_DAYS.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_handlers.edit_choosing_days)
            ],
            ConversationState.EDIT_CHOOSING_ONE_TIME_DATE.value: [
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
            MessageHandler(filters.Regex('^➕ Створити нагадування$'), handlers.create_reminder_start)
        ],
        states={
            ConversationState.DESCRIBING_TASK.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_description)
            ],
            ConversationState.CHOOSING_DAYS.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_days)
            ],
            ConversationState.CHOOSING_ONE_TIME_DATE.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_one_time_date)
            ],
            ConversationState.CHOOSING_TIMES.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_times)
            ],
            ConversationState.CHOOSING_INTERVAL.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_interval)
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex('^🏠 Скасувати$'), handlers.cancel),
            CommandHandler('cancel', handlers.cancel)
        ]
    )
    
    # Register handlers
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(MessageHandler(filters.Regex('^📋 Мої нагадування$'), handlers.view_reminders))
    application.add_handler(MessageHandler(filters.Regex('^🗑 Видалити нагадування$'), handlers.delete_reminder_start))
    
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
