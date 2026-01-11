import sqlite3
import sys
from pathlib import Path

# Добавляем путь к корню проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DB_PATH


def migrate():
    print(f"Migrating database (Adding CRM fields) at {DB_PATH}...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Добавляем customer_name в clients
    try:
        cursor.execute("ALTER TABLE clients ADD COLUMN customer_name VARCHAR(100)")
        print("✅ Added 'customer_name' column to 'clients' table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ Column 'customer_name' already exists in 'clients' table")
        else:
            print(f"❌ Error adding 'customer_name' to 'clients': {e}")

    # Добавляем event_date в client_children
    try:
        cursor.execute("ALTER TABLE client_children ADD COLUMN event_date VARCHAR(20)")
        print("✅ Added 'event_date' column to 'client_children' table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ Column 'event_date' already exists in 'client_children' table")
        else:
            print(f"❌ Error adding 'event_date' to 'client_children': {e}")

    conn.commit()
    conn.close()
    print("CRM fields migration completed.")


if __name__ == "__main__":
    migrate()
