import datetime
import os
import random
import re
from sqlalchemy.orm import Session
from sqlalchemy import func
from aiogram import Bot, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

# Імпорт моделей та станів
# ПРИМІТКА: Змінено відносні імпорти на припущення про ваш кореневий каталог
from ..database.models import User, Intern, Question, TestSession, AnswerOption, UserAnswer
from ..core.states import TestingStates
from ..database.session import get_db
from ..core.config import settings

QUESTIONS_PER_TEST = 20


# --- ДОПОМІЖНА ФУНКЦІЯ ЕКРАНУВАННЯ (ЗБЕРІГАЄ ОСНОВНУ РОЗМІТКУ) ---
def escape_markdown(text: str) -> str:
    """Екранує спеціальні символи MarkdownV2, крім тих, що використовуються для основної розмітки."""
    # Зберігаємо * та _ для жирного/курсиву, але екрануємо всі інші зарезервовані
    # Символи: _ * [ ] ( ) ~ ` > # + = - { | } . !
    # Ми НЕ екрануємо * і _ тут, щоб можна було використовувати **жирний** шрифт у фіксованих заголовках.
    # Для тексту з БД використовуйте окрему логіку або більш сувору функцію, як показано нижче.

    # Використовуємо суворіше екранування, яке вимагає Telegram для тексту з БД (як питання та варіанти)
    # Зберігаємо тільки пробіли та символи для нумерації (\.).
    return re.sub(r'([_*[\]()~`>#+=\-{|}.!])', r'\\\1', text)


# --- ДОПОМІЖНА ФУНКЦІЯ: Екранування ФІКСОВАНИХ СТРІНГОВИХ ЛІТЕРАЛІВ ---
def escape_fixed_text(text: str) -> str:
    """Екранує тільки критичні символи (. !) у фіксованих повідомленнях, зберігаючи розмітку (**)."""
    # Екрануємо лише крапки та знаки оклику, що можуть бути у фіксованих стрінгах,
    # та зворотні слеші, якщо вони вже є (для уникнення подвійного екранування, що може бути проблемою)
    text = text.replace('.', '\\.').replace('!', '\\!').replace('-', '\\-')
    # Для іконок та інших символів Telegram не вимагає екранування, якщо вони не є розміткою.
    return text


class TestingService:
    def __init__(self, db_session: Session, bot: Bot):
        self.db = db_session
        self.bot = bot

    def get_random_questions(self) -> list[Question]:
        return (
            self.db.query(Question)
            .order_by(func.random())
            .limit(QUESTIONS_PER_TEST)
            .all()
        )

    def check_test_status(self, user_telegram_id: int):
        user = self.db.query(User).filter(User.telegram_id == user_telegram_id).one_or_none()
        if not user:
            # ВИПРАВЛЕНО: Екранування крапки
            return {'status': 'error', 'message': "Ви не зареєстровані в системі\\."}

        completed_session = self.db.query(TestSession).filter(
            TestSession.user_id == user.id,
            TestSession.is_completed == True
        ).first()
        if completed_session:
            # ВИПРАВЛЕНО: Використовуємо escape_fixed_text, щоб уникнути збою
            message = escape_fixed_text("❌ **Цей тест є одноразовим.** Ви вже його склали.")
            # Потрібно також екранувати тут, оскільки ми можемо мати фіксовану розмітку
            return {'status': 'completed', 'message': message}

        active_session = self.db.query(TestSession).filter(
            TestSession.user_id == user.id,
            TestSession.is_completed == False
        ).order_by(TestSession.start_time.desc()).first()
        if active_session:
            return {'status': 'active', 'session': active_session}

        return {'status': 'available', 'user_id': user.id}

    def finalize_test_session(self, session: TestSession):
        if not session.is_completed:
            session.is_completed = True
            session.end_time = datetime.datetime.now()
            self.db.commit()
            print(f"✅ Сесія {session.id} завершена та зафіксована.")

    async def _send_next_question(self, user_id: int, fsm_context: FSMContext, session: TestSession,
                                  question: Question):
        # --- 1. Варіанти відповіді ---
        options = random.sample(question.options, len(question.options))
        options_text = ""
        buttons = []
        for idx, option in enumerate(options, start=1):
            # Текст варіанта екрануємо суворо
            escaped_option_text = escape_markdown(option.text)
            # ВИПРАВЛЕНО: Додано зворотний слеш перед крапкою для нумерації
            options_text += f"{idx}\\. {escaped_option_text}\n"

            button_text = f"Варіант {idx}"
            buttons.append([types.InlineKeyboardButton(text=button_text, callback_data=f"{question.id}:{option.id}")])

        # --- 2. Клавіатура ---
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)

        # --- 3. Заголовок і текст питання ---
        current_answer_count = self.db.query(UserAnswer).filter(UserAnswer.session_id == session.id).count()
        header = f"**Питання {current_answer_count + 1}/{QUESTIONS_PER_TEST}:**"

        # Текст питання екрануємо суворо
        escaped_question_text = escape_markdown(question.text)

        message_text = (
            f"{header}\n\n"
            f"{escaped_question_text}\n\n"
            f"**Оберіть правильний варіант:**\n"
            f"{options_text}"
        )

        # --- 4. Відправка фото або тексту ---
        photo_file_id = types.FSInputFile(question.photo_url) if question.photo_url and os.path.exists(
            question.photo_url) else None

        if photo_file_id:
            await self.bot.send_photo(
                chat_id=user_id,
                photo=photo_file_id,
                caption=message_text,
                reply_markup=keyboard,
                parse_mode="MarkdownV2"
            )
        else:
            await self.bot.send_message(
                chat_id=user_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode="MarkdownV2"
            )

        # --- 5. Оновлення FSM ---
        await fsm_context.set_state(TestingStates.in_test)

    async def check_and_start_tests(self):
        today = datetime.date.today()
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Планувальник: Початок перевірки стажерів...")

        for db in get_db():
            interns_to_test = (
                db.query(Intern)
                .filter(Intern.internship_end_date == today)
                .join(User)
                .all()
            )

            if not interns_to_test:
                print("   [Scheduler] Стажерів з датою закінчення сьогодні не знайдено.")
                return

            print(f"   [Scheduler] Знайдено {len(interns_to_test)} стажерів для тестування.")

            for intern in interns_to_test:
                user_id = intern.user.telegram_id
                status_result = self.check_test_status(user_id)
                status = status_result['status']

                if status == 'completed':
                    print(f"      [SKIP] Стажер {intern.full_name} ВЖЕ завершив тест.")
                    # Використовуємо повідомлення, яке вже було виправлено в check_test_status
                    await self.bot.send_message(
                        user_id,
                        status_result['message'],
                        parse_mode="MarkdownV2"
                    )
                    continue

                if status == 'active':
                    print(f"      [SKIP] Стажер {intern.full_name} має активну незавершену сесію.")
                    continue

                if status == 'error':
                    # ВИПРАВЛЕНО: Переконайтеся, що повідомлення з бази даних, якщо воно відправляється, екрановане.
                    # Оскільки тут відбувається `continue`, помилка не виникає.
                    print(f"      [ERROR] Стажер {intern.full_name} не зареєстрований: {status_result['message']}")
                    continue

                try:
                    test_questions = self.get_random_questions()
                    if len(test_questions) < QUESTIONS_PER_TEST:
                        print(f"      [ERROR] Недостатньо питань у базі ({len(test_questions)}).")
                        await self.bot.send_message(
                            user_id,
                            escape_fixed_text("На жаль, не вдалося розпочати тест: недостатньо питань у базі."),
                            parse_mode="MarkdownV2"
                        )
                        continue

                    new_session = TestSession(
                        user_id=intern.user.id,
                        max_score=QUESTIONS_PER_TEST,
                        start_time=datetime.datetime.now()
                    )
                    db.add(new_session)
                    db.commit()

                    # ВИПРАВЛЕНО: Екранування фіксованого тексту
                    await self.bot.send_message(
                        user_id,
                        escape_fixed_text("🔔 **Час для фінального тестування!**\nВи отримаєте 20 питань. Успіху!"),
                        parse_mode="MarkdownV2"
                    )

                    questions_id_list = [q.id for q in test_questions]

                    storage = self.bot.storage if hasattr(self.bot,
                                                          'storage') and self.bot.storage is not None else MemoryStorage()
                    fsm_key = StorageKey(bot_id=self.bot.id, chat_id=user_id, user_id=user_id)
                    fsm_context = FSMContext(storage=storage, key=fsm_key)

                    await fsm_context.set_data({
                        'session_id': new_session.id,
                        'questions_list': questions_id_list,
                        'current_q_index': 0
                    })
                    await fsm_context.set_state(TestingStates.in_test)

                    first_question = db.query(Question).get(questions_id_list[0])
                    await self._send_next_question(user_id, fsm_context, new_session, first_question)

                    print(f"      [SUCCESS] Запущено тест для {intern.full_name} (ID: {new_session.id}).")

                except Exception as e:
                    print(f"      [FATAL ERROR] Не вдалося запустити тест для {intern.full_name}: {e}")
                    # ВИПРАВЛЕНО: Екранування фіксованого тексту
                    await self.bot.send_message(
                        user_id,
                        escape_fixed_text(
                            "⚠️ Виникла системна помилка при запуску тесту. Зверніться до адміністратора."),
                        parse_mode="MarkdownV2"
                    )


class TestingSchedulerWrapper:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def run_scheduled_tests(self):
        for db in get_db():
            service = TestingService(db, self.bot)
            await service.check_and_start_tests()