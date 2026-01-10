#!/usr/bin/env python3
"""Запуск VK бота отдельно."""

import asyncio
import logging
import os
import sys

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from bot.vk_bot import run_vk_bot

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

if __name__ == "__main__":
    VK_TOKEN = os.getenv("VK_TOKEN")
    VK_GROUP_ID = os.getenv("VK_GROUP_ID")
    
    if not VK_TOKEN or not VK_GROUP_ID:
        print("❌ Необходимо указать VK_TOKEN и VK_GROUP_ID в .env файле!")
        sys.exit(1)
    
    print(f"🚀 Запуск VK бота для группы {VK_GROUP_ID}...")
    from bot.vk_bot import create_vk_bot
    bot = create_vk_bot(VK_TOKEN, int(VK_GROUP_ID))
    bot.run_forever()
