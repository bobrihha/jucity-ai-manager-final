"""Полная очистка всех заявок и клиентов."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DB_PATH

def clear_all_crm_data():
    """Удалить ВСЕ заявки и клиентов из БД."""
    print("⚠️  ВНИМАНИЕ: Удаление ВСЕХ заявок и клиентов...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Считаем что удаляем
    cursor.execute("SELECT COUNT(*) FROM leads")
    leads_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM clients")
    clients_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM client_phones")
    phones_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM client_children")
    children_count = cursor.fetchone()[0]
    
    # Удаляем все
    cursor.execute("DELETE FROM leads")
    cursor.execute("DELETE FROM client_children")
    cursor.execute("DELETE FROM client_phones")
    cursor.execute("DELETE FROM clients")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Удалено:")
    print(f"   - Заявки: {leads_count}")
    print(f"   - Клиенты: {clients_count}")
    print(f"   - Телефоны: {phones_count}")
    print(f"   - Дети: {children_count}")
    print("\n🎉 База данных очищена! Можно начинать с чистого листа.")

if __name__ == "__main__":
    clear_all_crm_data()
