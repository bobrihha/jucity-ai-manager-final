import sqlite3
import sys
from pathlib import Path

# Добавляем путь к корню проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DB_PATH

def backfill():
    print(f"Backfilling CRM data at {DB_PATH}...")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Получаем все уникальные telegram_id из leads и sessions
    # Используем словарь для хранения данных клиента: telegram_id -> {username, first_name...}
    clients_map = {}
    
    # Из sessions (там есть username)
    cursor.execute("SELECT telegram_id, username FROM sessions")
    for row in cursor.fetchall():
        tid = row["telegram_id"]
        if tid not in clients_map:
            clients_map[tid] = {"username": row["username"]}
        elif row["username"]:
            clients_map[tid]["username"] = row["username"]
            
    # Из leads (там тоже может быть username и есть имена)
    # Приоритет данных из leads (свежие)
    cursor.execute("SELECT telegram_id, username, customer_name, phone FROM leads")
    leads = cursor.fetchall()
    
    for row in leads:
        tid = row["telegram_id"]
        if not tid: continue
        
        if tid not in clients_map:
            clients_map[tid] = {}
        
        if row["username"]:
            clients_map[tid]["username"] = row["username"]
        if row["customer_name"]:
            clients_map[tid]["customer_name"] = row["customer_name"]
            # Простейшая эвристика имени
            parts = row["customer_name"].split()
            if len(parts) >= 1:
                clients_map[tid]["first_name"] = parts[0]
            if len(parts) >= 2:
                clients_map[tid]["last_name"] = " ".join(parts[1:])
        if row["phone"]:
            clients_map[tid]["phone"] = row["phone"]

    print(f"Found {len(clients_map)} unique clients to create.")
    
    # 2. Создаем клиентов
    created_count = 0
    for tid, data in clients_map.items():
        # Проверяем есть ли такой клиент
        cursor.execute("SELECT id FROM clients WHERE telegram_id = ?", (tid,))
        existing = cursor.fetchone()
        
        client_id = None
        if existing:
            client_id = existing["id"]
            # Можно обновить, но пока пропустим
        else:
            cursor.execute("""
                INSERT INTO clients (telegram_id, username, customer_name, first_name, last_name, phone)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                tid, 
                data.get("username"), 
                data.get("customer_name"),
                data.get("first_name"), 
                data.get("last_name"), 
                data.get("phone")
            ))
            client_id = cursor.lastrowid
            created_count += 1
            
        # 3. Привязываем Leads к этому клиенту
        cursor.execute("UPDATE leads SET client_id = ? WHERE telegram_id = ?", (client_id, tid))
        
        # 4. Добавляем телефоны из leads (история)
        cursor.execute("SELECT phone, created_at FROM leads WHERE telegram_id = ? AND phone IS NOT NULL", (tid,))
        phones = cursor.fetchall()
        for p_row in phones:
            p_val = p_row["phone"]
            # Проверяем дубликаты
            cursor.execute("SELECT id FROM client_phones WHERE client_id = ? AND phone = ?", (client_id, p_val))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO client_phones (client_id, phone, last_used_at) VALUES (?, ?, ?)", 
                               (client_id, p_val, p_row["created_at"]))

        # 5. Добавляем детей из leads
        cursor.execute("SELECT child_name, child_age, event_date FROM leads WHERE telegram_id = ? AND child_name IS NOT NULL", (tid,))
        children = cursor.fetchall()
        for c_row in children:
            c_name = c_row["child_name"]
            c_age = c_row["child_age"]
            c_event_date = c_row["event_date"]
            # Простейшая проверка дубликатов по имени и дате (если дата есть)
            if c_event_date:
                cursor.execute(
                    "SELECT id FROM client_children WHERE client_id = ? AND name = ? AND event_date = ?",
                    (client_id, c_name, c_event_date)
                )
            else:
                cursor.execute(
                    "SELECT id FROM client_children WHERE client_id = ? AND name = ? AND event_date IS NULL",
                    (client_id, c_name)
                )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO client_children (client_id, name, event_date, age) VALUES (?, ?, ?, ?)", 
                    (client_id, c_name, c_event_date, c_age)
                )

    conn.commit()
    conn.close()
    print(f"Backfill completed. Created {created_count} clients.")

if __name__ == "__main__":
    backfill()
