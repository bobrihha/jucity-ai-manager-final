"""Скрипт для сброса сессии пользователя (для тестирования)."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DB_PATH

def reset_user_session(user_id: str):
    """
    Сбросить историю диалогов для конкретного пользователя.
    user_id может быть telegram_id или vk_id (например: vk_123456)
    """
    print(f"Сброс сессии для пользователя {user_id}...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Находим сессию
    cursor.execute("SELECT id FROM sessions WHERE telegram_id = ?", (user_id,))
    session = cursor.fetchone()
    
    if not session:
        print(f"❌ Сессия для {user_id} не найдена")
        conn.close()
        return
    
    session_id = session[0]
    
    # Удаляем сообщения
    cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    deleted_messages = cursor.rowcount
    
    # Сбрасываем данные сессии
    cursor.execute("""
        UPDATE sessions 
        SET intent = 'unknown', lead_data = '{}' 
        WHERE id = ?
    """, (session_id,))
    
    conn.commit()
    conn.close()
    
    print(f"✅ Сброшено:")
    print(f"   - {deleted_messages} сообщений удалено")
    print(f"   - Intent сброшен на 'unknown'")
    print(f"   - lead_data очищен")
    print(f"\nТеперь можете начать диалог заново!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python reset_session.py <USER_ID>")
        print("Пример: python reset_session.py 461713084")
        print("Пример: python reset_session.py vk_123456")
        sys.exit(1)
    
    user_id = sys.argv[1]
    reset_user_session(user_id)
