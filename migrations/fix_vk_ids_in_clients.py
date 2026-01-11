import sqlite3
import sys
from pathlib import Path

# Добавляем путь к корню проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DB_PATH


def migrate():
    print(f"Fixing VK IDs in clients at {DB_PATH}...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE clients
        SET vk_id = telegram_id,
            telegram_id = NULL
        WHERE telegram_id LIKE 'vk_%'
          AND (vk_id IS NULL OR vk_id = '')
    """)
    updated = cursor.rowcount

    conn.commit()
    conn.close()

    print(f"Updated clients: {updated}")


if __name__ == "__main__":
    migrate()
