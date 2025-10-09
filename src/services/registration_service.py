from sqlalchemy.orm import Session
from sqlalchemy import func
# Імпорт моделей тут може викликати циклічну залежність,
# тому імпортуємо їх всередині функцій, або переносимо в 'models.py'
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
        Використовується в хендлері /start.
        """
        user = (
            self.db.query(User)
            .filter(User.telegram_id == telegram_id)
            .join(Intern)
            .first()
        )
        if user:
            return user.intern.full_name

        # Якщо користувача не знайдено, кидаємо помилку, щоб почати реєстрацію
        raise RegistrationError("Користувача не знайдено.")

    def register_user(self, telegram_id: int, telegram_tag: str | None, pin: str) -> str:
        """
        Реєструє користувача за ПІНом, виконуючи всі перевірки.

        Args:
            telegram_id: Унікальний ID користувача Telegram.
            telegram_tag: Тег користувача Telegram (може бути None).
            pin: ПІН стажера для ідентифікації.

        Returns:
            Повне ім'я стажера після успішної реєстрації.

        Raises:
            RegistrationError: Якщо перевірка не пройдена.
        """
        # 1. ПЕРЕВІРКА: Чи не зареєстрований цей Telegram ID вже
        if self.db.query(User).filter(User.telegram_id == telegram_id).first():
            raise RegistrationError("Цей Telegram-акаунт вже зареєстровано.")

        # 2. ПОШУК: Знайти стажера за ПІНом (порівняння без урахування регістру)
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
        except Exception:
            self.db.rollback()
            raise RegistrationError("Виникла внутрішня помилка при реєстрації. Спробуйте пізніше.")