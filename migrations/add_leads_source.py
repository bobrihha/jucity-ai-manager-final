import sqlite3
import sys
from pathlib import Path

# Добавляем путь к корню проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DB_PATH


def migrate():
    print(f"Migrating database (Adding leads.source) at {DB_PATH}...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE leads ADD COLUMN source VARCHAR(20) DEFAULT 'telegram'")
        print("✅ Added 'source' column to 'leads' table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ Column 'source' already exists in 'leads' table")
        else:
            print(f"❌ Error adding 'source' to 'leads': {e}")

    conn.commit()
    conn.close()
    print("Leads source migration completed.")


if __name__ == "__main__":
    migrate()
