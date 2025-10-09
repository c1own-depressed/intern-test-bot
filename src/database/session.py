from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base  # Імпортуємо Base з наших моделей
from src.core.config import settings # ⬅️ ЗМІНА 1: Імпортуємо налаштування

# --- 1. Налаштування URL та Engine ---

# ❌ Видалили локальне визначення DATABASE_URL, оскільки воно тепер береться з settings.

# Створення двигуна (Engine) SQLAlchemy. Engine - це інтерфейс до БД.
engine = create_engine(
    # ⬅️ ЗМІНА 2: Використовуємо рядок підключення з config.py (PostgreSQL)
    settings.DATABASE_URL
    # ❌ ЗМІНА 3: Видалили connect_args={"check_same_thread": False},
    # оскільки це специфічно для SQLite.
)

# --- 2. Створення фабрики сесій ---

# SessionLocal - це фабрика (клас), яка створює об'єкти Session.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- 3. Функція ініціалізації БД ---

def init_db():
    """Створює таблиці в базі даних на основі моделей, якщо вони ще не існують."""
    # Base.metadata.create_all() тепер створює схему, сумісну з PostgreSQL.
    Base.metadata.create_all(bind=engine)
    # Змінюємо повідомлення, щоб відображати нову БД
    print("База даних PostgreSQL та таблиці успішно ініціалізовані.")

# --- 4. Функція для отримання сесії ---

def get_db() -> Session:
    """
    Функція-генератор для отримання незалежної сесії бази даних.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()