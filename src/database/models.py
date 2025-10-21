import datetime
from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy import BigInteger
from sqlalchemy.orm import relationship, declarative_base

# База для декларативного визначення моделей
Base = declarative_base()


class Intern(Base):
    """Таблиця стажерів. Дані імпортуються з Google Drive."""
    __tablename__ = 'interns'

    id = Column(Integer, primary_key=True, index=True)
    pin = Column(String, unique=True, nullable=False, index=True)  # Унікальний ПІН
    full_name = Column(String, nullable=False)  # ПРІЗВИЩЕ ТА ІМЯ
    internship_end_date = Column(Date, nullable=False, index=True)  # ДАТА ОСТАННЬОГО ДНЯ СТАЖУВАННЯ

    # Зворотний зв'язок 1:1 з User
    user = relationship("User", back_populates="intern", uselist=False)


class User(Base):
    """Таблиця зареєстрованих користувачів бота."""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    # Змінено Integer на BigInteger для підтримки Telegram ID > 2.1 млрд.
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)  # ID користувача Telegram
    telegram_tag = Column(String, nullable=True)  # ТЕГ (username)

    # Зв'язок 1:1 з Intern. pin стає унікальним, оскільки він тут використовується
    intern_id = Column(Integer, ForeignKey('interns.id'), unique=True, nullable=False)
    intern = relationship("Intern", back_populates="user")

    # Зв'язок 1:N з TestSession
    sessions = relationship("TestSession", back_populates="user")


class Question(Base):
    """Таблиця питань для тестів."""
    __tablename__ = 'questions'

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)  # ТЕКСТ ПИТАННЯ
    photo_url = Column(String, nullable=True)  # Опціональний шлях/URL до фото

    # Зв'язок 1:N з AnswerOption
    options = relationship("AnswerOption", back_populates="question")


class AnswerOption(Base):
    """Таблиця варіантів відповідей для кожного питання."""
    __tablename__ = 'answer_options'

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)  # ІД ПИТАННЯ
    text = Column(String, nullable=False)  # ВАРІАНТ ВІДПОВІДІ
    is_correct = Column(Boolean, nullable=False, default=False)  # Правильна відповідь (TRUE/FALSE)

    question = relationship("Question", back_populates="options")


class TestSession(Base):
    """
    Таблиця, що фіксує одну спробу тестування.
    Тут зберігається загальний результат.
    """
    __tablename__ = 'test_sessions'

    id = Column(Integer, primary_key=True, index=True)
    # User ID в цій таблиці походить з таблиці users, де id має тип Integer,
    # тому тут можна залишити Integer.
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)  # Користувач

    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime, nullable=True)

    score = Column(Integer, default=0)  # Кількість правильних відповідей
    max_score = Column(Integer, default=20)  # Загальна кількість питань у тесті (20)
    is_completed = Column(Boolean, default=False)

    user = relationship("User", back_populates="sessions")
    answers = relationship("UserAnswer", back_populates="session")


class UserAnswer(Base):
    """
    Детальна відповідь користувача на одне питання в рамках сесії.
    Ця таблиця критична для формування детального звіту.
    """
    __tablename__ = 'user_answers'

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey('test_sessions.id'), nullable=False)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    # ID обраного варіанту відповіді
    selected_option_id = Column(Integer, ForeignKey('answer_options.id'), nullable=False)

    is_correct = Column(Boolean, nullable=False)  # Чи була відповідь правильною

    session = relationship("TestSession", back_populates="answers")
    question = relationship("Question")
    selected_option = relationship("AnswerOption")
