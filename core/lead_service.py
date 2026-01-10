"""
Сервис для работы с заявками (Lead).
Обеспечивает надёжное сохранение и обновление данных.
"""

import logging
from datetime import datetime
from typing import Optional
from db import SessionLocal, Lead

logger = logging.getLogger(__name__)


def get_or_create_lead(user_id: str, source: str = "telegram", park_id: str = "nn") -> Lead:
    """
    Получить или создать лид для пользователя.
    Если есть незавершённый лид (статус 'new') — вернуть его.
    Иначе — создать новый.
    """
    db = SessionLocal()
    try:
        # Ищем незавершённый лид для этого пользователя
        lead = db.query(Lead).filter(
            Lead.telegram_id == user_id,
            Lead.status == "new"
        ).order_by(Lead.created_at.desc()).first()
        
        if not lead:
            # Создаём новый лид
            lead = Lead(
                telegram_id=user_id,
                source=source,
                park_id=park_id,
                status="new"
            )
            db.add(lead)
            db.commit()
            db.refresh(lead)
            logger.info(f"Created new lead #{lead.id} for user {user_id}")
        
        return lead
    finally:
        db.close()


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
