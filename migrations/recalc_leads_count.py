import sqlite3
import sys
from pathlib import Path

# Добавляем путь к корню проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DB_PATH

def fix_counts():
    print(f"Recalculating total_leads at {DB_PATH}...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # SQL-магия для обновления счетчика одним запросом (работает в SQLite)
    cursor.execute("""
    UPDATE clients
    SET total_leads = (
        SELECT COUNT(*)
        FROM leads
        WHERE leads.client_id = clients.id
    )
    """)
    
    rows = cursor.rowcount
    
    conn.commit()
    conn.close()
    print(f"Updated total_leads for {rows} clients.")

if __name__ == "__main__":
    fix_counts()
