"""Добавление недостающих колонок в БД на сервере."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "bot.db"

def migrate():
    """Добавить недостающие колонки в таблицы."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("🔧 Синхронизация схемы БД...")
    
    # Проверяем и добавляем customer_name в clients
    try:
        cursor.execute("SELECT customer_name FROM clients LIMIT 1")
        print("✅ clients.customer_name уже существует")
    except sqlite3.OperationalError:
        print("➕ Добавляю clients.customer_name...")
        cursor.execute("ALTER TABLE clients ADD COLUMN customer_name VARCHAR(100)")
        print("✅ clients.customer_name добавлена")
    
    # Проверяем и добавляем event_date в client_children
    try:
        cursor.execute("SELECT event_date FROM client_children LIMIT 1")
        print("✅ client_children.event_date уже существует")
    except sqlite3.OperationalError:
        print("➕ Добавляю client_children.event_date...")
        cursor.execute("ALTER TABLE client_children ADD COLUMN event_date VARCHAR(50)")
        print("✅ client_children.event_date добавлена")
    
    conn.commit()
    conn.close()
    
    print("\n🎉 Миграция завершена успешно!")

if __name__ == "__main__":
    migrate()
