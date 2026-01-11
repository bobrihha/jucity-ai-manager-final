import sqlite3
import sys
from pathlib import Path

# Добавляем путь к корню проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DB_PATH

def migrate():
    print(f"Migrating database (CRM tables) at {DB_PATH}...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Таблица clients
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id VARCHAR(50) UNIQUE,
        vk_id VARCHAR(50) UNIQUE,
        username VARCHAR(100),
        customer_name VARCHAR(100),
        first_name VARCHAR(100),
        last_name VARCHAR(100),
        phone VARCHAR(20),
        total_leads INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    print("✅ Created/Verified 'clients' table")
    
    # Индексы для clients
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_telegram_id ON clients (telegram_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_vk_id ON clients (vk_id)")

    # 2. Таблица client_phones
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS client_phones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        phone VARCHAR(20),
        last_used_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(client_id) REFERENCES clients(id)
    )
    """)
    print("✅ Created/Verified 'client_phones' table")

    # 3. Таблица client_children
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS client_children (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        name VARCHAR(100),
        event_date VARCHAR(20),
        birth_date DATE,
        age INTEGER,
        FOREIGN KEY(client_id) REFERENCES clients(id)
    )
    """)
    print("✅ Created/Verified 'client_children' table")

    # 4. Добавляем client_id в leads
    try:
        cursor.execute("ALTER TABLE leads ADD COLUMN client_id INTEGER REFERENCES clients(id)")
        print("✅ Added 'client_id' column to 'leads' table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ Column 'client_id' already exists in 'leads' table")
        else:
            print(f"❌ Error adding column to 'leads': {e}")
            
    conn.commit()
    conn.close()
    print("CRM Migration completed.")

if __name__ == "__main__":
    migrate()
