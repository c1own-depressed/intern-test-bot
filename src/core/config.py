from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Клас для завантаження та зберігання конфігураційних змінних.
    Автоматично завантажує змінні з файлу .env.
    """
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True
    )

    # --- 1. Telegram та Bot Core ---
    BOT_TOKEN: str

    # --- 2. Налаштування Бази Даних ---
    DATABASE_URL: str

    # --- 3. Налаштування Планувальника (Scheduling) ---
    # 🕒 ЗМІНЕНО: Час розсилки тепер встановлено для київської часової зони.
    SCHEDULE_TIME: time = time(hour=16, minute=1, second=0, tzinfo=ZoneInfo("Europe/Kiev"))

    # --- 4. Налаштування Google Sheets/Drive ---
    # 🔒 ЗМІНЕНО: Тепер завантажуємо вміст credentials.json з цієї змінної, а не з файлу.
    # У вашому .env файлі ця змінна має містити весь JSON у вигляді рядка.
    GOOGLE_CREDENTIALS_JSON: str

    # ID Google Sheets, звідки імпортуємо дані стажерів
    INTERN_SHEET_ID: str

    # Назва аркуша в таблиці, де знаходяться стажери
    INTERN_WORKSHEET_NAME: str = "БД Стажери"

    # ID Google DOCS, звідки імпортуємо питання
    QUESTION_DOC_ID: str

    # ID Google Doc для запису звітів
    REPORT_DOC_ID: str = "1onNj_UAcsNv6xioHBv8HowETMlmll5M8IOY4Nb_2pxE"

    # 📂 ЗМІНЕНО: Шлях буде відносним у .env, але абсолютним у програмі
    # Шлях до директорії, де будемо зберігати фотографії
    PHOTO_DIR: str = "data/question_photos"


# Створюємо єдиний екземпляр налаштувань, який буде використовуватися у всьому проєкті.
settings = Settings()


# --- Трансформація шляхів для надійності на сервері ---

# Визначаємо кореневу директорію проєкту (папка, яка містить `src`)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Перетворюємо відносний шлях PHOTO_DIR на абсолютний.
# Це гарантує, що програма завжди знайде цю папку, незалежно від того, звідки її запущено.
absolute_photo_dir = BASE_DIR / settings.PHOTO_DIR

# Оновлюємо значення в налаштуваннях та одразу створюємо директорію, якщо її немає.
settings.PHOTO_DIR = str(absolute_photo_dir)
absolute_photo_dir.mkdir(parents=True, exist_ok=True)