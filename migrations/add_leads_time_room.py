import sqlite3
import sys
from pathlib import Path

# Добавляем путь к корню проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DB_PATH


def migrate():
    print(f"Migrating database (Adding leads.time/room) at {DB_PATH}...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE leads ADD COLUMN time VARCHAR(20)")
        print("✅ Added 'time' column to 'leads' table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ Column 'time' already exists in 'leads' table")
        else:
            print(f"❌ Error adding 'time' to 'leads': {e}")

    try:
        cursor.execute("ALTER TABLE leads ADD COLUMN room VARCHAR(50)")
        print("✅ Added 'room' column to 'leads' table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ Column 'room' already exists in 'leads' table")
        else:
            print(f"❌ Error adding 'room' to 'leads': {e}")

    conn.commit()
    conn.close()
    print("Leads time/room migration completed.")


if __name__ == "__main__":
    migrate()
