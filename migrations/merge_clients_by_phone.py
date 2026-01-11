import sqlite3
import sys
import re
from pathlib import Path

# Добавляем путь к корню проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DB_PATH

def normalize_phone(phone: str):
    if not phone: return None
    digits = re.sub(r"\D", "", str(phone))
    if not digits: return None
    if len(digits) >= 10:
        return digits[-10:]
    return digits

def merge_clients():
    print(f"Merging clients by phone at {DB_PATH}...")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Получаем всех клиентов с телефонами
    cursor.execute("SELECT * FROM clients WHERE phone IS NOT NULL")
    clients = cursor.fetchall()
    
    # Группируем по нормализованному телефону
    phone_map = {}
    for cl in clients:
        norm = normalize_phone(cl["phone"])
        if not norm: continue
        
        if norm not in phone_map:
            phone_map[norm] = []
        phone_map[norm].append(dict(cl))
        
    merged_count = 0
    deleted_count = 0
        
    for phone, group in phone_map.items():
        if len(group) < 2:
            continue
            
        # Нашли дубликаты!
        print(f"Found duplicates for phone ending {phone}: {len(group)} clients")
        
        # Сортируем: сначала те у кого больше данных (есть telegram_id, vk_id), потом старые
        # Эвристика: Master - тот у кого есть ID. Если у обоих - берем первого (старого)
        # Или объединяем данные.
        
        # Сначала выберем Master
        # Приоритет: есть telegram_id > есть vk_id > oldest created_at
        group.sort(key=lambda x: (
            x["telegram_id"] is not None, 
            x["vk_id"] is not None, 
            x["id"]  # меньше ID = старше (обычно)
        ), reverse=True)
        
        master = group[0]
        duplicates = group[1:]
        
        print(f"  Master: {master['id']} ({master['first_name']})")
        
        for dup in duplicates:
            print(f"  Merging {dup['id']} ({dup['first_name']}) -> {master['id']}")
            
            # 1. Переносим LEADS
            cursor.execute("UPDATE leads SET client_id = ? WHERE client_id = ?", (master["id"], dup["id"]))
            
            # 2. Переносим CHILDREN
            cursor.execute("UPDATE client_children SET client_id = ? WHERE client_id = ?", (master["id"], dup["id"]))
            
            # 3. Переносим PHONES (история)
            cursor.execute("UPDATE client_phones SET client_id = ? WHERE client_id = ?", (master["id"], dup["id"]))
            
            # 4. Объединяем данные в Master (если в Master пусто, а в Dup есть)
            updates = []
            params = []
            
            if not master["telegram_id"] and dup["telegram_id"]:
                updates.append("telegram_id = ?")
                params.append(dup["telegram_id"])
                master["telegram_id"] = dup["telegram_id"] # Update local dict too logic
                
            if not master["vk_id"] and dup["vk_id"]:
                updates.append("vk_id = ?")
                params.append(dup["vk_id"])
                master["vk_id"] = dup["vk_id"]
                
            if not master["username"] and dup["username"]:
                updates.append("username = ?")
                params.append(dup["username"])

            if not master.get("customer_name") and dup.get("customer_name"):
                updates.append("customer_name = ?")
                params.append(dup["customer_name"])
                
            if not master["first_name"] and dup["first_name"]:
                updates.append("first_name = ?")
                params.append(dup["first_name"])
                
            if not master["last_name"] and dup["last_name"]:
                updates.append("last_name = ?")
                params.append(dup["last_name"])
            
            if updates:
                sql = f"UPDATE clients SET {', '.join(updates)} WHERE id = ?"
                params.append(master["id"])
                cursor.execute(sql, tuple(params))
                
            # 5. Удаляем Dup
            cursor.execute("DELETE FROM clients WHERE id = ?", (dup["id"],))
            deleted_count += 1
            
        # Обновляем счетчик для Master
        cursor.execute("""
            UPDATE clients 
            SET total_leads = (SELECT COUNT(*) FROM leads WHERE client_id = ?)
            WHERE id = ?
        """, (master["id"], master["id"]))
        
        merged_count += 1
        
    conn.commit()
    conn.close()
    print(f"Merge completed. Merged {merged_count} groups, deleted {deleted_count} duplicates.")

if __name__ == "__main__":
    merge_clients()
