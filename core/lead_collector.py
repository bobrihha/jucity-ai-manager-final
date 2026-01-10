"""Lead Collector — сбор данных для заявки на праздник."""

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime


@dataclass 
class LeadData:
    """Данные заявки на праздник."""
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    child_name: Optional[str] = None
    child_age: Optional[int] = None
    event_date: Optional[str] = None
    kids_count: Optional[int] = None
    adults_count: Optional[int] = None
    format: Optional[str] = None  # room, restaurant
    extras: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "LeadData":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def get_missing_fields(self) -> list[str]:
        """Получить список недостающих обязательных полей."""
        missing = []
        if not self.customer_name:
            missing.append("имя для связи")
        if not self.child_name:
            missing.append("имя именинника")
        if not self.event_date:
            missing.append("дата праздника")
        if not self.kids_count:
            missing.append("количество детей")
        return missing
    
    def get_optional_missing(self) -> list[str]:
        """Получить список желательных полей."""
        missing = []
        if not self.phone:
            missing.append("телефон")
        if not self.child_age:
            missing.append("возраст именинника")
        if not self.adults_count:
            missing.append("количество взрослых")
        if not self.format:
            missing.append("формат (комната или ресторан)")
        return missing
    
    def is_ready_for_manager(self) -> bool:
        """Готов ли лид для передачи менеджеру."""
        # Минимум: имя + телефон + дата
        return bool(self.customer_name and self.phone and self.event_date)
    
    def get_summary(self) -> str:
        """Получить краткое описание для уведомления."""
        lines = ["🎉 *Новая заявка на праздник*\n"]
        
        if self.customer_name:
            lines.append(f"👤 Контакт: {self.customer_name}")
        if self.phone:
            lines.append(f"📞 Телефон: {self.phone}")
        if self.child_name:
            age_str = f" ({self.child_age} лет)" if self.child_age else ""
            lines.append(f"👶 Именинник: {self.child_name}{age_str}")
        if self.event_date:
            lines.append(f"📅 Дата: {self.event_date}")
        if self.kids_count:
            lines.append(f"👧 Детей: {self.kids_count}")
        if self.adults_count:
            lines.append(f"👨 Взрослых: {self.adults_count}")
        if self.format:
            format_name = "Комната" if self.format == "room" else "Ресторан" if self.format == "restaurant" else self.format
            lines.append(f"📍 Формат: {format_name}")
        if self.extras:
            lines.append(f"✨ Доп. услуги: {', '.join(self.extras)}")
        
        return "\n".join(lines)


class LeadCollector:
    """Управление сбором данных лида."""
    
    def __init__(self):
        self.leads: dict[str, LeadData] = {}
    
    def get_lead(self, session_id: str) -> LeadData:
        """Получить или создать лид для сессии."""
        if session_id not in self.leads:
            self.leads[session_id] = LeadData()
        return self.leads[session_id]
    
    def update_lead(self, session_id: str, data: dict) -> LeadData:
        """Обновить данные лида."""
        lead = self.get_lead(session_id)
        
        for key, value in data.items():
            if hasattr(lead, key) and value is not None:
                if key == "extras" and isinstance(value, list):
                    # Добавляем к существующим, не дублируем
                    current_extras = set(lead.extras or [])
                    current_extras.update(value)
                    lead.extras = list(current_extras)
                else:
                    setattr(lead, key, value)
        
        return lead
    
    def clear_lead(self, session_id: str):
        """Очистить данные лида."""
        if session_id in self.leads:
            del self.leads[session_id]


# Глобальный экземпляр
lead_collector = LeadCollector()
