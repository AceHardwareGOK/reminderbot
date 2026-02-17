import os
from dotenv import load_dotenv

# Allow choosing a specific env file (for example, .env.test)
ENV_FILE = os.getenv("ENV_FILE", ".env")
load_dotenv(ENV_FILE)

DB_PATH = os.getenv("DB_PATH", "reminders.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
