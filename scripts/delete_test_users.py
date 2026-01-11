"""Удаление всех данных клиента (для тестирования)."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DB_PATH

def delete_user_data(user_id: str):
    """
    Полностью удалить все данные пользователя:
    - Клиентскую карточку
    - Все заявки
    - Историю телефонов
    - Детей
    """
    print(f"Удаление данных для пользователя {user_id}...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Находим клиента
    cursor.execute("""
        SELECT id FROM clients 
        WHERE telegram_id = ? OR vk_id = ?
    """, (user_id, user_id))
    client = cursor.fetchone()
    
    if not client:
        print(f"❌ Клиент {user_id} не найден")
        conn.close()
        return
    
    client_id = client[0]
    
    # Удаляем заявки
    cursor.execute("DELETE FROM leads WHERE client_id = ?", (client_id,))
    deleted_leads = cursor.rowcount
    
    # Удаляем телефоны
    cursor.execute("DELETE FROM client_phones WHERE client_id = ?", (client_id,))
    deleted_phones = cursor.rowcount
    
    # Удаляем детей
    cursor.execute("DELETE FROM client_children WHERE client_id = ?", (client_id,))
    deleted_children = cursor.rowcount
    
    # Удаляем клиента
    cursor.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    
    conn.commit()
    conn.close()
    
    print(f"✅ Удалено для {user_id}:")
    print(f"   - Клиент: 1")
    print(f"   - Заявки: {deleted_leads}")
    print(f"   - Телефоны: {deleted_phones}")
    print(f"   - Дети: {deleted_children}")

if __name__ == "__main__":
    # Список тестовых аккаунтов
    test_users = [
        "461713084",      # @Bobryhha
        "5261935873",     # @CACHALOT_ai
        "6651485984",     # @fnikitakan
        "7417013020",     # @ooomirmir
        "vk_76767383",    # VK
    ]
    
    for user in test_users:
        delete_user_data(user)
    
    print("\n✅ Все тестовые данные удалены!")
