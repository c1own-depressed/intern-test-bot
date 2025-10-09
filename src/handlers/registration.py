from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session
from typing import Callable, Any
from functools import wraps
import re

# Імпорт компонентів з нашої архітектури
from ..core.states import RegistrationStates
from ..services.registration_service import RegistrationService, RegistrationError
from ..database.session import get_db

# Створення роутера для збору хендлерів
registration_router = Router()


# --- ДОПОМІЖНА ФУНКЦІЯ: Екранування MarkdownV2 ---
def escape_markdown_v2(text: str) -> str:
    """Екранує символи, зарезервовані в Telegram MarkdownV2."""
    # Список всіх зарезервованих символів
    # Тут ми екрануємо ВСІ символи, які можуть бути в імені, щоб вони не ламали розмітку
    reserved_chars = r"([_*[\]()~`>#+\-=|{}.!])"
    return re.sub(reserved_chars, r'\\\1', text)


# --- Функція для отримання сесії БД (без змін) ---
def with_db_session(func: Callable):
    """
    Декоратор для автоматичного отримання сесії БД та її закриття.
    """

    @wraps(func)
    async def wrapper(message: types.Message, state: FSMContext, *args, **kwargs: Any):
        for db_session in get_db():
            return await func(message=message, state=state, db_session=db_session)

    return wrapper


# --- 1. Обробка команди /start (Залишаємо без змін) ---
@registration_router.message(CommandStart())
@with_db_session
async def handle_start(message: types.Message, state: FSMContext, db_session: Session):
    user_id = message.from_user.id
    service = RegistrationService(db_session)

    try:
        intern_name = service.get_intern_name_by_telegram_id(user_id)

        # ⬅️ ВИПРАВЛЕННЯ: Екрануємо змінну intern_name
        safe_intern_name = escape_markdown_v2(intern_name)

        await state.set_state(RegistrationStates.main_menu)
        # Використовуємо f-рядок із raw-рядками, але тепер з екранованою змінною
        await message.answer(
            f"З поверненням, **{safe_intern_name}**\! Ви вже успішно зареєстровані\."
        )

    except RegistrationError:
        await state.set_state(RegistrationStates.awaiting_pin)
        # Повідомлення про початок реєстрації (без змін)
        await message.answer(
            r"👋 **Вітаю\!**" + "\n" + r"Щоб почати, будь ласка, **введіть свій унікальний ПІН** для ідентифікації\."
        )


# --- 2. Обробка вводу ПІНа (ВИПРАВЛЕНА ФУНКЦІЯ) ---
@registration_router.message(RegistrationStates.awaiting_pin, F.text)
@with_db_session
async def handle_pin_input(message: types.Message, state: FSMContext, db_session: Session):
    pin = message.text.strip()
    user_id = message.from_user.id
    username = message.from_user.username

    service = RegistrationService(db_session)

    try:
        # Реєстрація успішна, дані записуються в БД
        full_name = service.register_user(
            telegram_id=user_id,
            telegram_tag=username,
            pin=pin
        )

        # Екрануємо отримане ім'я, щоб у ньому не було символів, які ламають розмітку
        safe_full_name = escape_markdown_v2(full_name)

        # Встановлення наступного стану
        await state.set_state(RegistrationStates.main_menu)

        # ❗ КЛЮЧОВЕ ВИПРАВЛЕННЯ: Використовуємо єдиний raw f-string для безпечної відправки
        await message.answer(
            f"✅ **Реєстрація успішна\!**\n\n"  # Використовуємо \n\n для нового рядка
            f"Вітаємо, **{safe_full_name}**\. Ваш обліковий запис активовано\."
        )

    except RegistrationError as e:
        # Обробка помилок бізнес-логіки (ПІН не знайдено, ПІН зайнятий тощо)
        safe_error_message = escape_markdown_v2(str(e))

        await message.answer(
            r"❌ **Помилка реєстрації**\: " + safe_error_message + "\n" + r"Спробуйте ввести ПІН ще раз або зверніться до адміністратора\."
        )

    except Exception:
        # Загальна системна помилка (на випадок, якщо щось піде не так)
        # Повідомлення про помилку залишається, але тепер воно має спрацьовувати рідше
        await message.answer(r"⚠️ Виникла невідома помилка\. Спробуйте пізніше\.")