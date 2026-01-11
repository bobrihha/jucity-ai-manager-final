"""
Сервис для работы с заявками (Lead).
Обеспечивает надёжное сохранение и обновление данных.
"""

import logging
from datetime import datetime
from typing import Optional
from db import SessionLocal, Lead, Client, ClientPhone, ClientChild

logger = logging.getLogger(__name__)


def ensure_client(db, telegram_id: str, username: str = None, phone: str = None, first_name: str = None, last_name: str = None) -> Client:
    """Гарантировать существование клиента и обновить его данные."""
    client = db.query(Client).filter(Client.telegram_id == str(telegram_id)).first()
    
    if not client:
        client = Client(
            telegram_id=str(telegram_id),
            username=username,
            first_name=first_name,
            last_name=last_name,
            phone=phone
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        logger.info(f"Created new Client #{client.id} for telegram_id {telegram_id}")
    else:
        # Обновляем данные если пришли новые
        changed = False
        if username and client.username != username:
            client.username = username
            changed = True
        if first_name and not client.first_name:
            client.first_name = first_name
            changed = True
        if last_name and not client.last_name:
            client.last_name = last_name
            changed = True
        if phone and not client.phone:
            client.phone = phone
            changed = True
            
        if changed:
            client.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(client)
            
    return client


def get_or_create_lead(user_id: str, source: str = "telegram", park_id: str = "nn", username: str = None) -> Lead:
    """Получить существующий или создать новый лид."""
    db = SessionLocal()
    
    # 1. Гарантируем клиента
    client = ensure_client(db, user_id, username=username)
    
    # Ищем активный лид (статус new или contacted)
    lead = db.query(Lead).filter(
        Lead.telegram_id == user_id,
        Lead.park_id == park_id,
        Lead.status.in_(["new", "contacted"])
    ).first()
    
    if not lead:
        lead = Lead(
            telegram_id=str(user_id),
            park_id=park_id,
            source=source,
            username=username,
            status="new",
            client_id=client.id  # Связываем с клиентом
        )
        db.add(lead)
        # Увеличиваем счетчик лидов у клиента
        client.total_leads += 1
        db.commit()
        db.refresh(lead)
    else:
        # Если лид есть, но без client_id (старый) — привязываем
        if not lead.client_id:
            lead.client_id = client.id
            db.commit()
            
        # Обновляем username если появился
        if username and lead.username != username:
            lead.username = username
            db.commit()
            db.refresh(lead)
            
    db.close()
    return lead


def update_lead_from_data(lead_id: int, data: dict) -> Lead:
    """
    Обновить лид данными из словаря.
    Обновляет только непустые поля.
    """
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            logger.error(f"Lead #{lead_id} not found!")
            return None
        
        # Маппинг полей
        field_mapping = {
            "customer_name": "customer_name",
            "phone": "phone",
            "child_name": "child_name",
            "child_age": "child_age",
            "event_date": "event_date",
            "time": "time",
            "room": "room",
            "kids_count": "kids_count",
            "adults_count": "adults_count",
            "format": "format",
            "extras": "extras",
        }
        
        updated_fields = []
        for data_key, model_key in field_mapping.items():
            value = data.get(data_key)
            if value is not None and value != "" and value != []:
                current_value = getattr(lead, model_key, None)
                if current_value != value:
                    setattr(lead, model_key, value)
                    updated_fields.append(f"{model_key}={value}")
        
        if updated_fields:
            lead.updated_at = datetime.utcnow()
            
            # --- CRM LOGIC: Обновляем данные клиента ---
            if lead.client_id:
                client = db.query(Client).filter(Client.id == lead.client_id).first()
                if client:
                    # 1. Если обновился телефон
                    new_phone = data.get("phone")
                    if new_phone:
                        # Обновляем основной телефон если не был задан
                        if not client.phone:
                            client.phone = new_phone
                            db.add(client)
                        
                        # Добавляем в историю телефонов
                        # Проверяем нет ли уже такого телефона у этого клиента
                        existing_phone = db.query(ClientPhone).filter(
                            ClientPhone.client_id == client.id, 
                            ClientPhone.phone == new_phone
                        ).first()
                        
                        if not existing_phone:
                            db.add(ClientPhone(client_id=client.id, phone=new_phone))
                        else:
                            # Обновляем дату использования
                            existing_phone.last_used_at = datetime.utcnow()

                    # 2. Если обновился ребенок
                    new_child = data.get("child_name")
                    new_age = data.get("child_age")
                    if new_child:
                        # Проверяем есть ли такой ребенок
                        existing_child = db.query(ClientChild).filter(
                             ClientChild.client_id == client.id,
                             ClientChild.name == new_child
                        ).first()
                        
                        if not existing_child:
                            db.add(ClientChild(client_id=client.id, name=new_child, age=new_age))
                        elif new_age:
                            # Обновляем возраст если изменился
                            existing_child.age = new_age
            
            db.commit()
            logger.info(f"Updated lead #{lead.id}: {', '.join(updated_fields)}")
        
        db.refresh(lead)
        return lead
    finally:
        db.close()


def mark_lead_sent_to_manager(lead_id: int) -> bool:
    """Пометить лид как отправленный менеджеру."""
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.sent_to_manager = True
            lead.updated_at = datetime.utcnow()
            db.commit()
            logger.info(f"Lead #{lead.id} marked as sent to manager")
            return True
        return False
    finally:
        db.close()


def lead_to_dict(lead: Lead) -> dict:
    """Преобразовать Lead в словарь для уведомлений."""
    return {
        "customer_name": lead.customer_name,
        "phone": lead.phone,
        "child_name": lead.child_name,
        "child_age": lead.child_age,
        "event_date": lead.event_date,
        "time": lead.time,
        "room": lead.room,
        "kids_count": lead.kids_count,
        "adults_count": lead.adults_count,
        "format": lead.format,
        "extras": lead.extras or [],
    }


def get_lead_by_id(lead_id: int) -> Optional[Lead]:
    """Получить лид по ID."""
    db = SessionLocal()
    try:
        return db.query(Lead).filter(Lead.id == lead_id).first()
    finally:
        db.close()
