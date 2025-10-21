import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError  # <<< 1. ДОДАНО ІМПОРТ

# Припускаємо, що ваші моделі знаходяться на рівень вище у 'database/models'
from ..database.models import User, Intern


# --- Власне Виключення (Exception) для кращої обробки помилок ---
class RegistrationError(Exception):
    """Спеціальний клас помилок для реєстрації."""
    pass


class RegistrationService:
    def __init__(self, db_session: Session):
        """Ініціалізація сервісу з сесією бази даних."""
        self.db = db_session

    def get_intern_name_by_telegram_id(self, telegram_id: int) -> str:
        """
        Перевіряє, чи користувач вже зареєстрований, і повертає його повне ім'я.
        """
        user = (
            self.db.query(User)
            .filter(User.telegram_id == telegram_id)
            .join(Intern)
            .first()
        )
        if user:
            return user.intern.full_name

        raise RegistrationError("Користувача не знайдено.")

    def register_user(self, telegram_id: int, telegram_tag: str | None, pin: str) -> str:
        """
        Реєструє користувача за ПІНом, виконуючи всі перевірки.
        """
        # 1. ПЕРЕВІРКА: Чи не зареєстрований цей Telegram ID вже
        if self.db.query(User).filter(User.telegram_id == telegram_id).first():
            raise RegistrationError("Цей Telegram-акаунт вже зареєстровано.")

        # 2. ПОШУК: Знайти стажера за ПІНом
        intern_record = (
            self.db.query(Intern)
            .filter(func.lower(Intern.pin) == func.lower(pin))
            .first()
        )

        if not intern_record:
            raise RegistrationError("ПІН не знайдено. Перевірте правильність вводу.")

        # 3. ПЕРЕВІРКА: Чи не використовується цей ПІН іншим користувачем
        if intern_record.user:
            raise RegistrationError("Цей ПІН вже успішно використано для реєстрації.")

        # 4. РЕЄСТРАЦІЯ: Створення запису в таблиці User
        try:
            new_user = User(
                telegram_id=telegram_id,
                telegram_tag=telegram_tag,
                intern_id=intern_record.id,
            )
            self.db.add(new_user)
            self.db.commit()
            return intern_record.full_name

        except IntegrityError as e:  # <<< 2. ЯВНА ОБРОБКА IntegrityError
            self.db.rollback()
            # Логування повної помилки `e` тут дуже рекомендоване!
            print(f"Помилка IntegrityError при реєстрації: {e}")
            raise RegistrationError("Помилка цілісності даних. Цей ПІН або Telegram ID вже використовується.")

        except Exception as e:
            self.db.rollback()
            # Логування повної помилки `e` тут дуже рекомендоване!
            print(f"Невідома внутрішня помилка при реєстрації: {e}")
            raise RegistrationError("Виникла внутрішня помилка при реєстрації. Спробуйте пізніше.")
