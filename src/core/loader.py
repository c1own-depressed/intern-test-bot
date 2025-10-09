from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.client.default import DefaultBotProperties

from .config import settings
from ..database.session import init_db, SessionLocal
from ..handlers.registration import registration_router
from ..handlers.common import common_router
from ..handlers.testing import testing_router
from ..services.testing_service import TestingSchedulerWrapper
# ❗️ 1. ІМПОРТУЄМО ОБИДВА ІМПОРТЕРИ
from ..utils.google_doc_importer import GoogleDocsImporter
from ..utils.google_sheet_importer import import_interns_data

# --- 1. Ініціалізація Основних Об'єктів ---

bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="MarkdownV2")
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
bot.storage = storage
scheduler = AsyncIOScheduler()
testing_wrapper = TestingSchedulerWrapper(bot=bot)


# --- ДОПОМІЖНІ ФУНКЦІЇ-ОБГОРТКИ ДЛЯ ПЛАНУВАЛЬНИКА ---

def scheduled_import_interns():
    """Обгортка для запланованого імпорту стажерів з Google Sheets."""
    print("🔄 Запланований імпорт: Оновлення даних стажерів...")
    try:
        import_interns_data(SessionLocal)
        print("   [Scheduled Import] Дані стажерів успішно оновлені.")
    except Exception as e:
        print(f"   [Scheduled Import] 🔴 ПОМИЛКА ІМПОРТУ СТАЖЕРІВ: {e}")


# ❗️ 2. НОВА ФУНКЦІЯ: Обгортка для запланованого імпорту питань
def scheduled_import_questions():
    """Обгортка для запланованого імпорту питань з Google Docs."""
    print("🔄 Запланований імпорт: Оновлення питань з Google Docs...")
    try:
        docs_importer = GoogleDocsImporter()
        with SessionLocal() as db:
            docs_importer.import_questions(db)
        print("   [Scheduled Import] Питання успішно оновлені.")
    except Exception as e:
        print(f"   [Scheduled Import] 🔴 ПОМИЛКА ІМПОРТУ ПИТАНЬ: {e}")


# -----------------------------------------------


# --- 2. Функція Створення та Налаштування ---

async def setup_system():
    """
    Збирає всі компоненти системи, реєструє хендлери та ініціалізує БД.
    """
    print("🚀 Запуск ініціалізації системи...")

    # 2.1. Ініціалізація Бази Даних
    init_db()
    print("   [DB] База даних і таблиці ініціалізовані.")

    # 2.2. Первинний імпорт даних під час старту
    print("   [DB] Спроба первинного імпорту даних...")
    try:
        # Імпорт стажерів
        import_interns_data(SessionLocal)
        print("   [DB] Дані стажерів успішно імпортовані.")
        # Імпорт питань
        docs_importer = GoogleDocsImporter()
        with SessionLocal() as db:
            docs_importer.import_questions(db)
        print("   [DB] Питання успішно імпортовані.")
    except Exception as e:
        print(f"   [DB] 🔴 ПОМИЛКА ПЕРВИННОГО ІМПОРТУ: {e}")

    # 2.3. Реєстрація Роутерів
    dp.include_router(common_router)
    dp.include_router(registration_router)
    dp.include_router(testing_router)
    print("   [Handlers] Роутери підключені: common, registration, testing.")

    # 2.4. Додавання запланованих завдань

    # Завдання для оновлення стажерів
    scheduler.add_job(
        scheduled_import_interns,
        'cron',
        hour=18,  # Можеш змінити час, якщо потрібно
        minute=59,
        id='google_sheets_update'
    )
    print("   [Scheduler] Оновлення стажерів заплановано на 18:59.")

    # ❗️ 3. НОВЕ ЗАВДАННЯ: Планувальник для оновлення питань о 18:00
    scheduler.add_job(
        scheduled_import_questions,
        'cron',
        hour=18,
        minute=0,
        id='google_docs_update'
    )
    print("   [Scheduler] Оновлення питань заплановано на 18:00.")

    # Завдання для запуску тестів
    scheduler.add_job(
        testing_wrapper.run_scheduled_tests,
        'cron',
        hour=settings.SCHEDULE_TIME.hour,
        minute=settings.SCHEDULE_TIME.minute,
        id='run_final_tests'
    )

    # 2.5. Запуск Планувальника
    scheduler.start()
    print(f"   [Scheduler] Планувальник запущено. Тести заплановано на {settings.SCHEDULE_TIME}.")

    print("✅ Ініціалізація завершена.")


# --- 3. Функція Запуску ---

async def start_bot():
    """
    Точка входу для запуску бота.
    """
    await dp.start_polling(bot)