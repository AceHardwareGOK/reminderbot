import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv('DB_PATH', 'reminders.db')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
