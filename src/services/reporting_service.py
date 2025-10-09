# services/reporting_service.py

import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from aiogram import Bot
import re
import io

# Імпорт компонентів з нашої архітектури
from ..database.models import User, Intern, TestSession, UserAnswer, Question, AnswerOption
from ..core.config import settings
from ..database.session import get_db

# --- ІМПОРТИ ДЛЯ GOOGLE DOCS API ---
# Встановіть: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ----------------------------------------

# SCOPE для Google Docs API:
DOCS_SCOPE = ["https://www.googleapis.com/auth/documents"]


class ReportingService:
    def __init__(self, db_session: Session, bot: Bot):
        self.db = db_session
        self.bot = bot
        self.docs_service = self._authenticate_google_docs()

    def _authenticate_google_docs(self):
        """Аутентифікація для доступу до Google Docs API."""
        try:
            creds = Credentials.from_service_account_file(
                settings.GOOGLE_CREDENTIALS_FILE,
                scopes=DOCS_SCOPE
            )
            return build('docs', 'v1', credentials=creds)
        except Exception as e:
            print(f"❌ ПОМИЛКА АУТЕНТИФІКАЦІЇ GOOGLE DOCS: {e}")
            return None

    def _escape_md(self, text: str) -> str:
        """Екранує спеціальні символи MarkdownV2."""
        if not text:
            return ""
        return re.sub(r'([_*[\]()~`>#+=\-{|}.!])', r'\\\1', text)

    # 🎯 МЕТОД ДЛЯ TELEGRAM
    def generate_detailed_report(self, session_id: int) -> str | None:
        """
        Формує повний детальний звіт про сесію тестування, використовуючи MarkdownV2.
        """
        session = self.db.query(TestSession).filter(TestSession.id == session_id).one_or_none()
        if not session:
            return None

        user: User = session.user
        intern: Intern = user.intern

        intern_name = intern.full_name if intern else f"Користувач без профілю (ID: {user.telegram_id})"

        score = session.score or 0
        max_score = session.max_score or 1
        percentage = round((score / max_score) * 100, 2) if max_score > 0 else 0

        time_spent = "—"
        if session.start_time and session.end_time:
            duration = session.end_time - session.start_time
            total_seconds = int(duration.total_seconds())
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            time_spent = f"{minutes} хв {seconds} сек"

        report_parts = []

        # --- ШАПКА ---
        header = (
            f"🚀 *Звіт про проходження тесту*\n\n"
            f"-----------------------------------------\n"
            f"👤 *Стажер:* {self._escape_md(intern_name)}\n"
            f"🆔 *Telegram ID:* `{user.telegram_id}`\n"
            f"-----------------------------------------\n"
            f"🌟 *Результат:* *{score}/{max_score}* \\({percentage}\\%\\)\n"
            f"⏱️ *Час:* `{self._escape_md(time_spent)}`\n"
            f"📅 *Дата/Час:* {session.end_time.strftime('%Y\\-%m\\-%d %H:%M:%S') if session.end_time else '—'}\n"
            f"-----------------------------------------\n\n"
        )
        report_parts.append(header)

        # --- ВІДПОВІДІ ---
        answers_data = self.db.query(UserAnswer).filter(UserAnswer.session_id == session_id).order_by(
            UserAnswer.id).all()

        for i, answer in enumerate(answers_data, 1):
            question: Question = answer.question
            selected_option: AnswerOption = answer.selected_option
            correct_option: AnswerOption = (
                self.db.query(AnswerOption)
                .filter(AnswerOption.question_id == question.id, AnswerOption.is_correct == True)
                .first()
            )

            status_emoji = "🟢" if answer.is_correct else "🔴"

            detail = (
                f"{status_emoji} *{i}\\. Питання:* {self._escape_md(question.text)}\n"
                f"   \\- *Відповідь стажера:* {self._escape_md(selected_option.text)}\n"
                f"   \\- *Статус:* {'✅ Правильно' if answer.is_correct else '❌ Неправильно'}\n"
                f"   \\- *Правильний варіант:* {self._escape_md(correct_option.text if correct_option else 'N/A')}\n\n"
            )
            report_parts.append(detail)

        return "".join(report_parts)

    # 🎯 ОНОВЛЕНИЙ КРАСИВИЙ ЗВІТ ДЛЯ GOOGLE DOC
    def _generate_report_for_doc(self, session_id: int) -> str | None:
        """
        Формує гарно структурований звіт для Google Doc.
        """
        session = self.db.query(TestSession).filter(TestSession.id == session_id).one_or_none()
        if not session:
            return None

        user: User = session.user
        intern: Intern = user.intern
        intern_name = intern.full_name if intern else f"Користувач без профілю (ID: {user.telegram_id})"

        score = session.score or 0
        max_score = session.max_score or 1
        percentage = round((score / max_score) * 100, 2) if max_score > 0 else 0

        time_spent = "—"
        if session.start_time and session.end_time:
            duration = session.end_time - session.start_time
            total_seconds = int(duration.total_seconds())
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            time_spent = f"{minutes} хв {seconds} сек"

        report_parts = []

        # --- ШАПКА ---
        report_parts.append("📑 ЗВІТ ПРО ПРОХОДЖЕННЯ ТЕСТУ\n\n")
        report_parts.append(f"👤 Стажер: {intern_name}\n")
        report_parts.append(f"🆔 Telegram ID: {user.telegram_id}\n")
        report_parts.append(f"📅 Дата тестування: {session.end_time.strftime('%Y-%m-%d %H:%M:%S') if session.end_time else '—'}\n")
        report_parts.append(f"⭐ Результат: {score}/{max_score} ({percentage}%)\n")
        report_parts.append(f"⏱️ Час: {time_spent}\n\n")

        report_parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n")

        # --- СПИСОК ПИТАНЬ ---
        answers_data = self.db.query(UserAnswer).filter(UserAnswer.session_id == session_id).order_by(
            UserAnswer.id).all()

        for i, answer in enumerate(answers_data, 1):
            question: Question = answer.question
            selected_option: AnswerOption = answer.selected_option
            correct_option: AnswerOption = self.db.query(AnswerOption).filter(
                AnswerOption.question_id == question.id, AnswerOption.is_correct == True
            ).first()

            status = '✅ ПРАВИЛЬНО' if answer.is_correct else '❌ НЕПРАВИЛЬНО'

            detail = (
                f"📌 Питання {i}\n"
                f"━━━━━━━━━━━━━━\n"
                f"🔹 Текст питання:\n"
                f"   {question.text}\n\n"
                f"🔹 Відповідь стажера:\n"
                f"   {selected_option.text}\n\n"
                f"🔹 Правильний варіант:\n"
                f"   {correct_option.text if correct_option else 'N/A'}\n\n"
                f"🔹 Статус: {status}\n\n"
            )
            report_parts.append(detail)

        report_parts.append("📌 Кінець звіту\n")

        return "".join(report_parts)

    async def _write_to_google_doc(self, doc_id: str, report_content: str):
        """
        Додає текст у кінець вказаного Google Doc.
        """
        if not self.docs_service:
            print("❌ Google Docs Service не ініціалізовано. Пропуск запису.")
            return

        requests = [
            {
                'insertText': {
                    'text': report_content + "\n\n",
                    'endOfSegmentLocation': {}
                }
            }
        ]

        try:
            self.docs_service.documents().batchUpdate(
                documentId=doc_id, body={'requests': requests}
            ).execute()
            print(f"✅ Звіт успішно записано у Google Doc ID: {doc_id}")
        except HttpError as err:
            print(f"❌ Помилка Google Docs API: {err}")
            raise
        except Exception as e:
            print(f"❌ Невідома помилка при записі у Google Doc: {e}")
            raise

    async def send_report_to_admin(self, session_id: int):
        """
        Генерує звіт, надсилає його адміністратору (Telegram)
        та записує його у Google Doc.
        """
        telegram_report = self.generate_detailed_report(session_id)
        doc_report = self._generate_report_for_doc(session_id)

        try:
            admin_id = settings.ADMIN_CHAT_ID
        except AttributeError:
            admin_id = None

        if telegram_report and admin_id:
            try:
                await self.bot.send_message(
                    chat_id=admin_id,
                    text=telegram_report,
                    parse_mode="MarkdownV2"
                )
                print(f"✅ Звіт про сесію {session_id} успішно надіслано адміністратору ({admin_id}).")
            except Exception as e:
                print(f"❌ Помилка надсилання звіту адміністратору: {e}")

        if doc_report and hasattr(settings, 'REPORT_DOC_ID') and settings.REPORT_DOC_ID:
            try:
                await self._write_to_google_doc(settings.REPORT_DOC_ID, doc_report)
            except Exception as e:
                print(f"❌ Не вдалося записати звіт у Google Doc: {e}")


# 🎯 Допоміжна функція
async def finalise_session_and_report(session_id: int, bot: Bot):
    """
    Обгортка, що надає сесію БД, створює ReportingService та надсилає звіт.
    """
    for db in get_db():
        reporting_service = ReportingService(db, bot)
        await reporting_service.send_report_to_admin(session_id)
        break
