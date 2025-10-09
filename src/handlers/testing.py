from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime
import re  # Додано для екранування

# Імпорт компонентів нашої архітектури
from ..core.states import TestingStates
from ..database.session import get_db
from ..database.models import TestSession, Question, AnswerOption, UserAnswer, User
from ..services.testing_service import TestingService
from ..services.reporting_service import finalise_session_and_report

# Константа для кількості питань у тесті (для перевірки відновлення)
# ПРИМІТКА: Ця константа має бути оголошена в core/config.py або services/testing_service.py
# Припускаємо, що тут вона визначена для прикладу, якщо її немає у services/testing_service.py.
try:
    from ..services.testing_service import QUESTIONS_PER_TEST
except ImportError:
    QUESTIONS_PER_TEST = 20  # Запасне значення, якщо константа відсутня в сервісі

# Роутер для логіки тестування
testing_router = Router()


# Допоміжна функція для екранування MarkdownV2
def escape_markdown(text: str) -> str:
    """Екранує спеціальні символи MarkdownV2, крім тих, що використовуються для основної розмітки."""
    # Екрануємо символи, які можуть бути в тексті з БД і викликати помилки парсингу
    return re.sub(r'([_*[\]()~`>#+=\-{|}.!])', r'\\\1', text)


# ----------------------------------------------------------------------------------------------------------------------
# Обробник: /start_test - для перевірки статусу тесту (блокування/продовження), АЛЕ НЕ ДЛЯ ЗАПУСКУ НОВОГО
# ----------------------------------------------------------------------------------------------------------------------
@testing_router.message(F.text == "/start_test")
async def handle_start_test(message: types.Message, state: FSMContext, bot: Bot):
    """
    Обробник для перевірки статусу тесту.
    Дозволяє продовжити активну сесію або блокує, якщо тест завершено.
    """
    user_id = message.from_user.id

    for db in get_db():
        service = TestingService(db, bot)

        # 1. ПЕРЕВІРКА СТАТУСУ ТЕСТУ (Completed, Active, Available)
        result = service.check_test_status(user_id)
        status = result['status']

        if status == 'completed':
            # Тест вже пройдено (одноразовість)
            await message.answer(result['message'])
            return

        elif status == 'active':
            # ✅ Логіка відновлення активної сесії
            session: TestSession = result['session']

            data = await state.get_data()
            questions_list = data.get('questions_list')
            answered_count = db.query(UserAnswer).filter(UserAnswer.session_id == session.id).count()

            # Якщо FSM-стан втрачено, ми не можемо відновити questions_list і це проблема.
            if not questions_list:
                # Фінальна перевірка, чи не потрібно завершити сесію
                if answered_count == QUESTIONS_PER_TEST:
                    service.finalize_test_session(session)
                    await message.answer("⚠️ Сесія відновлена, але вона повинна бути завершена. Фіналізуємо.")
                    return

                await message.answer(
                    "⚠️ Помилка: Ваш тест не може бути відновлений (відсутні дані). Зверніться до адміністратора.")
                return

            if answered_count < len(questions_list):
                # 1. Відновлюємо повний FSM стан
                await state.set_state(TestingStates.in_test)
                await state.set_data({
                    'session_id': session.id,
                    'questions_list': questions_list,
                    'current_q_index': answered_count  # відновлюємо індекс на основі кількості відповідей
                })

                await message.answer(
                    f"⏳ У вас вже є активна сесія тестування (ID: {session.id}). Продовжуємо з питання **{answered_count + 1}**.")

                # 2. Надсилаємо наступне питання
                next_question_id = questions_list[answered_count]
                next_question = db.query(Question).filter(Question.id == next_question_id).first()

                await service._send_next_question(user_id, state, session, next_question)
                return

            # Якщо відповідей стільки ж, скільки питань, але сесія не зафіксована як completed
            await message.answer(
                "⚠️ Помилка: Сесія має бути завершена, але не зафіксована. Будь ласка, зверніться до адміністратора.")
            return

        elif status == 'available':
            await message.answer(
                "ℹ️ **Фінальний тест запускається автоматично!**\n\n"
                "Очікуйте повідомлення з питанням сьогодні о 16:00."
            )
            return

        elif status == 'error':
            await message.answer(result['message'])
            return


# ----------------------------------------------------------------------------------------------------------------------
# Обробник відповідей: фіналізує сесію через сервіс
# ----------------------------------------------------------------------------------------------------------------------
@testing_router.callback_query(
    TestingStates.in_test,
)
async def handle_answer(callback_query: types.CallbackQuery, state: FSMContext, bot: Bot):
    """
    Обробляє натискання на кнопку-варіант відповіді під час тестування.
    """
    # 1. Обов'язкова відповідь на callback_query, щоб прибрати "годинник"
    await callback_query.answer()

    # 2. Вилучення даних із FSM та Callback
    data = await state.get_data()
    session_id = data.get('session_id')
    questions_list = data.get('questions_list')
    current_q_index = data.get('current_q_index')

    # Фінальна перевірка FSM даних
    if session_id is None or questions_list is None or current_q_index is None:
        await callback_query.message.answer("⚠️ Помилка: Втрачено дані тесту. Зверніться до адміністратора.")
        await state.clear()
        return

    try:
        current_question_id, answer_option_id = map(int, callback_query.data.split(':'))
    except ValueError:
        await callback_query.message.answer("⚠️ Помилка обробки відповіді. Спробуйте пізніше.")
        return

    # 3. Перевірка коректності та збереження відповіді
    for db in get_db():
        service = TestingService(db, bot)
        session: TestSession = db.query(TestSession).filter(TestSession.id == session_id).first()
        question: Question = db.query(Question).filter(Question.id == current_question_id).first()
        answer_option: AnswerOption = db.query(AnswerOption).filter(AnswerOption.id == answer_option_id).first()

        if not session or not question or not answer_option:
            await callback_query.message.answer("⚠️ Помилка: Сесія, питання або варіант відповіді не знайдено.")
            return

        # 3.1. Запобігання повторному натисканню (логіка протидії race condition)
        # Перевіряємо, чи питання, на яке користувач щойно відповів, є поточним питанням у списку FSM.
        if current_q_index != questions_list.index(current_question_id):
            # Якщо користувач натиснув кнопку повторно або відповів на старе питання
            # Редагування повідомлення (або його ігнорування)
            try:
                await callback_query.message.edit_text(
                    "✅ Вашу відповідь прийнято (ігнорується повторне натискання).",
                    reply_markup=None
                )
            except Exception:
                pass  # Ігноруємо помилки редагування
            return

        # 3.2. Перевірка, чи не було вже збережено відповіді на це питання
        existing_answer = db.query(UserAnswer).filter(
            UserAnswer.session_id == session_id,
            UserAnswer.question_id == current_question_id
        ).first()

        if existing_answer:
            try:
                await callback_query.message.edit_text(
                    "✅ Вашу відповідь вже було збережено (ігнорується повторна спроба).",
                    reply_markup=None
                )
            except Exception:
                pass
            return

        # 3.3. Збереження відповіді
        user_answer = UserAnswer(
            session_id=session_id,
            question_id=current_question_id,
            selected_option_id=answer_option_id,
            is_correct=answer_option.is_correct
        )
        db.add(user_answer)

        # 3.4. Оновлення рахунку
        session.score = (session.score or 0) + (1 if answer_option.is_correct else 0)
        db.commit()

        # 3.5. Видалення кнопок та позначення відповіді
        try:
            # Отримуємо вихідний текст
            message_content = callback_query.message.caption if callback_query.message.caption else callback_query.message.text

            # Екрануємо оригінальний текст питання та текст відповіді
            escaped_message_content = escape_markdown(message_content)
            escaped_answer_text = escape_markdown(answer_option.text)

            # Формуємо фінальний текст, де тільки розмітка закреслення (~~) і жирного (**),
            # а решта вмісту екранована.
            final_text = (
                f"~~{escaped_message_content}~~\n\n"
                f"**✅ Ваша відповідь:** {escaped_answer_text}"
            )

            await callback_query.message.edit_text(
                final_text,
                reply_markup=None,
                parse_mode="MarkdownV2"
            )
        except Exception as e:
            # Це критичний блок для уникнення збоїв
            print(f"⚠️ Помилка редагування повідомлення: {e}")
            try:
                # Спроба відправити нове, просте повідомлення, якщо редагування не вдалося
                await callback_query.message.answer("✅ Відповідь прийнято. Перехід до наступного питання...")
            except Exception:
                pass

        # 4. Визначення наступного кроку
        next_q_index = current_q_index + 1

        if next_q_index < len(questions_list):
            # 4.1. Надсилання наступного питання
            await state.update_data(current_q_index=next_q_index)

            next_question_id = questions_list[next_q_index]
            next_question = db.query(Question).filter(Question.id == next_question_id).first()

            await service._send_next_question(
                user_id=callback_query.from_user.id,
                fsm_context=state,
                session=session,
                question=next_question
            )

        else:
            # 4.2. Завершення тесту (КРИТИЧНА ТОЧКА для одноразовості та звітності)

            # ФІНАЛІЗАЦІЯ СЕСІЇ (встановлює is_completed=True)
            service.finalize_test_session(session)

            await state.clear()

            # НАДСИЛАННЯ ЗВІТУ АДМІНІСТРАТОРУ
            await finalise_session_and_report(session.id, bot)

            # 4.3. Повідомлення про результат (користувачеві)
            result_text = (
                # ВИПРАВЛЕНО: Екранування '!' у фінальному повідомленні
                f"🎉 **Тест завершено\\!**\n\n"
                f"Ваш результат: **{session.score or 0}/{session.max_score}**\n\n"
                f"Звіт успішно сформовано та надіслано адміністратору\\."
            )
            await callback_query.message.answer(result_text, parse_mode="MarkdownV2")

            print(
                f"✅ Тест для користувача {callback_query.from_user.id} завершено. Результат: {session.score}/{session.max_score}")