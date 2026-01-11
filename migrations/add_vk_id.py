import sqlite3
import sys
from pathlib import Path

# Добавляем путь к корню проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DB_PATH

def migrate():
    print(f"Migrating database (Adding vk_id) at {DB_PATH}...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Добавляем vk_id в clients
    try:
        cursor.execute("ALTER TABLE clients ADD COLUMN vk_id VARCHAR(50)")
        print("✅ Added 'vk_id' column to 'clients' table")
        
        # Индекс для vk_id
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_clients_vk_id ON clients (vk_id)")
        print("✅ Created index on 'vk_id'")
        
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ Column 'vk_id' already exists in 'clients' table")
        else:
            print(f"❌ Error adding column to 'clients': {e}")
            
    conn.commit()
    conn.close()
    print("Migration completed.")

if __name__ == "__main__":
    migrate()
