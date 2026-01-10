"""Database connection and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import DB_PATH
from db.models import Base

# SQLite connection
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Инициализировать базу данных."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Получить сессию БД."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
