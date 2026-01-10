"""Telegram Bot — точка входа."""

import logging
from telegram import BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from bot.handlers import (
    start_command, handle_message, button_handler, error_handler,
    birthday_command, human_command, dynamic_command_handler
)
from config.settings import TELEGRAM_BOT_TOKEN
from db import init_db, SessionLocal, BotCommand

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def post_init(application):
    """Инициализация после создания приложения."""
    # Устанавливаем меню команд из БД
    db = SessionLocal()
    try:
        db_commands = db.query(BotCommand).filter(BotCommand.is_active == True).order_by(BotCommand.order).all()
        
        commands = []
        if db_commands:
            for cmd in db_commands:
                commands.append(BotCommand(cmd.command, cmd.title))
        else:
            # Дефолтные команды для первого запуска
            commands = [
                BotCommand("start", "🏠 Главное меню"),
                BotCommand("prices", "💰 Цены"),
                BotCommand("birthday", "🎂 День рождения"),
                # ... остальные можно добавить или оставить пустым если БД пустая
            ]
            
        await application.bot.set_my_commands(commands)
        logger.info(f"Bot menu commands set successfully! ({len(commands)} commands)")
    except Exception as e:
        logger.error(f"Failed to set commands: {e}")
    finally:
        db.close()
    
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
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("birthday", birthday_command))
    application.add_handler(CommandHandler("human", human_command))
    
    # Универсальный обработчик для остальных команд из БД
    application.add_handler(MessageHandler(filters.COMMAND, dynamic_command_handler))
    
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Bot is running! Press Ctrl+C to stop.")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
