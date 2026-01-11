import sqlite3
import sys
from pathlib import Path

# Добавляем путь к корню проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DB_PATH

def migrate():
    print(f"Migrating database at {DB_PATH}...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Добавляем username в таблицу sessions
    try:
        cursor.execute("ALTER TABLE sessions ADD COLUMN username VARCHAR(100)")
        print("✅ Added 'username' column to 'sessions' table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ Column 'username' already exists in 'sessions' table")
        else:
            print(f"❌ Error adding column to 'sessions': {e}")

    # 2. Добавляем username в таблицу leads
    try:
        cursor.execute("ALTER TABLE leads ADD COLUMN username VARCHAR(100)")
        print("✅ Added 'username' column to 'leads' table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ Column 'username' already exists in 'leads' table")
        else:
            print(f"❌ Error adding column to 'leads': {e}")
            
    conn.commit()
    conn.close()
    print("Migration completed.")

if __name__ == "__main__":
    migrate()
