"""Telegram Bot — точка входа."""

import logging
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from bot.handlers import start_command, handle_message, button_handler, error_handler
from config.settings import TELEGRAM_BOT_TOKEN
from db import init_db

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def post_init(application):
    """Инициализация после создания приложения."""
    logger.info("Bot initialized successfully!")


def main():
    """Запуск бота."""
    # Проверяем токен
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN not configured! Please set it in .env file")
        print("\n❌ Ошибка: Не настроен TELEGRAM_BOT_TOKEN!")
        print("1. Скопируйте .env.example в .env")
        print("2. Добавьте токен бота от @BotFather")
        print("3. Добавьте OpenAI API ключ")
        return
    
    # Инициализируем БД
    logger.info("Initializing database...")
    init_db()
    
    # Создаём приложение
    logger.info("Starting bot...")
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Bot is running! Press Ctrl+C to stop.")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
