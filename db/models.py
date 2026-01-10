"""Database models."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Session(Base):
    """Сессия пользователя."""
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(50), unique=True, index=True)
    park_id = Column(String(10), default="nn")
    intent = Column(String(20), default="unknown")  # birthday, general, unknown
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Данные сбора лида
    lead_data = Column(JSON, default=dict)
    
    messages = relationship("Message", back_populates="session")


class Message(Base):
    """Сообщение в диалоге."""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    role = Column(String(20))  # user, assistant
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    session = relationship("Session", back_populates="messages")


class Lead(Base):
    """Лид (заявка на праздник)."""
    __tablename__ = "leads"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(50), index=True)  # или vk_123456
    park_id = Column(String(10), default="nn")
    source = Column(String(20), default="telegram")  # telegram, vk
    
    # Контактные данные
    customer_name = Column(String(100))
    phone = Column(String(20))
    
    # Данные праздника
    child_name = Column(String(100))
    child_age = Column(Integer)
    event_date = Column(String(50))
    time = Column(String(20))  # 10:30, 14:30, 18:30
    room = Column(String(50))  # Опушка, Поляна Чудес и т.д.
    kids_count = Column(Integer)
    adults_count = Column(Integer)
    format = Column(String(20))  # room, restaurant, unknown
    extras = Column(JSON, default=list)  # аниматор, торт, шары...
    
    # Статус
    status = Column(String(20), default="new")  # new, contacted, booked, cancelled
    notes = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sent_to_manager = Column(Boolean, default=False)


class Document(Base):
    """Документ базы знаний."""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True)
    park_id = Column(String(10), default="nn")
    category = Column(String(20))  # general, birthday, shared
    title = Column(String(200))
    content = Column(Text)
    source_file = Column(String(500))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
