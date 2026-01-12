"""Настройки приложения."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

# Пути
BASE_DIR = Path(__file__).parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
DB_PATH = BASE_DIR / "data" / "bot.db"

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# VK
VK_TOKEN = os.getenv("VK_TOKEN", "")
VK_GROUP_ID = os.getenv("VK_GROUP_ID", "")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Парк по умолчанию
DEFAULT_PARK_ID = os.getenv("DEFAULT_PARK_ID", "nn")

# Уведомления менеджерам
MANAGER_CHAT_ID = os.getenv("MANAGER_CHAT_ID", "")

# Создаём директорию для БД если нет
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
