from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session
from typing import Callable, Any
from functools import wraps
import re

# Імпорт компонентів з нашої архітектури
from ..core.states import RegistrationStates  # Припускаємо, що states тут
from ..services.registration_service import RegistrationService, RegistrationError
from ..database.session import get_db  # Припускаємо, що get_db тут

# Створення роутера для збору хендлерів
registration_router = Router()


# --- ДОПОМІЖНА ФУНКЦІЯ: Екранування MarkdownV2 ---
def escape_markdown_v2(text: str) -> str:
    """Екранує символи, зарезервовані в Telegram MarkdownV2."""
    reserved_chars = r"([_*[\]()~`>#+\-=|{}.!])"
    return re.sub(reserved_chars, r'\\\1', text)


# --- Функція для отримання сесії БД (без змін) ---
def with_db_session(func: Callable):
    """
    Декоратор для автоматичного отримання сесії БД та її закриття.
    """

    @wraps(func)
    async def wrapper(message: types.Message, state: FSMContext, *args, **kwargs: Any):
        # Ітерація по генератору get_db() для отримання сесії
        for db_session in get_db():
            return await func(message=message, state=state, db_session=db_session)

    return wrapper


# --- 1. Обробка команди /start ---
@registration_router.message(CommandStart())
@with_db_session
async def handle_start(message: types.Message, state: FSMContext, db_session: Session):
    user_id = message.from_user.id
    service = RegistrationService(db_session)

    try:
        intern_name = service.get_intern_name_by_telegram_id(user_id)
        safe_intern_name = escape_markdown_v2(intern_name)

        await state.set_state(RegistrationStates.main_menu)

        await message.answer(
            f"З поверненням, {safe_intern_name}\! Ви вже успішно зареєстровані\.",
            parse_mode="MarkdownV2"
        )

    except RegistrationError:
        await state.set_state(RegistrationStates.awaiting_pin)

        await message.answer(
            r"👋 Вітаю\!" + "\n" + r"Щоб почати, будь ласка, введіть свій унікальний ПІН для ідентифікації\.",
            parse_mode="MarkdownV2"
        )


# --- 2. Обробка вводу ПІНа ---
@registration_router.message(RegistrationStates.awaiting_pin, F.text)
@with_db_session
async def handle_pin_input(message: types.Message, state: FSMContext, db_session: Session):
    pin = message.text.strip()
    user_id = message.from_user.id
    username = message.from_user.username

    service = RegistrationService(db_session)

    try:
        # Реєстрація успішна
        full_name = service.register_user(
            telegram_id=user_id,
            telegram_tag=username,
            pin=pin
        )

        safe_full_name = escape_markdown_v2(full_name)

        await state.set_state(RegistrationStates.main_menu)

        await message.answer(
            f"✅ Реєстрація успішна\!\n\n"
            f"Вітаємо, {safe_full_name}\. Ваш обліковий запис активовано\.",
            parse_mode="MarkdownV2"
        )

    except RegistrationError as e:
        # Обробка помилок бізнес-логіки (ПІН не знайдено, ПІН зайнятий, IntegrityError)
        safe_error_message = escape_markdown_v2(str(e))

        await message.answer(
            r"❌ Помилка реєстрації\: " + safe_error_message + "\n" + r"Спробуйте ввести ПІН ще раз або зверніться до адміністратора\.",
            parse_mode="MarkdownV2"
        )

    except Exception:
        # Загальна системна помилка (на випадок, якщо щось піде не так)
        await message.answer(
            r"⚠️ Виникла невідома помилка\. Спробуйте пізніше\.",
            parse_mode="MarkdownV2"
        )
