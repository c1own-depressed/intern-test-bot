import gspread
import os
import re
import requests
import json
import traceback  # ❗️ ДОДАНО: Для детального звіту про помилки
from datetime import datetime, timedelta
from typing import Callable, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..core.config import settings
from ..database.models import Intern
from ..database.session import get_db


class ImportError(Exception):
    """Спеціальний клас помилок для імпорту даних."""
    pass


# --------------------------------------------------------------------------------
# КЛАС ІМПОРТУ
# --------------------------------------------------------------------------------

class GoogleSheetImporter:
    def __init__(self):
        """Ініціалізація клієнтів Google API."""
        try:
            # 1. Завантажуємо дані для автентифікації зі змінної оточення
            credentials_info = json.loads(settings.GOOGLE_CREDENTIALS_JSON)
        except json.JSONDecodeError:
            raise ImportError("Помилка парсингу GOOGLE_CREDENTIALS_JSON. Перевірте формат змінної у .env.")
        except AttributeError:
            raise ImportError("Змінна GOOGLE_CREDENTIALS_JSON не знайдена в налаштуваннях.")

        # 2. Визначаємо необхідні права доступу
        self.scopes = [
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/documents.readonly',
            'https://www.googleapis.com/auth/drive.readonly'
        ]

        # 3. Авторизація для всіх API через словник
        self.creds = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=self.scopes
        )

        # 4. Створюємо клієнти для кожного сервісу Google
        self.gspread_client = gspread.service_account_from_dict(credentials_info, scopes=self.scopes)
        self.docs_service = build('docs', 'v1', credentials=self.creds)
        self.drive_service = build('drive', 'v3', credentials=self.creds)

        # 5. Підготовка директорії для фото
        os.makedirs(settings.PHOTO_DIR, exist_ok=True)

    # -------------------------------------------
    # ІМПОРТ СТАЖЕРІВ (GOOGLE SHEETS)
    # -------------------------------------------

    def import_interns(self, db: Session):
        """
        Імпортує дані стажерів з Google Sheets.
        """
        print("      [Importer] Початок імпорту даних стажерів...")

        try:
            sheet = self.gspread_client.open_by_key(settings.INTERN_SHEET_ID)
            try:
                worksheet = sheet.worksheet(settings.INTERN_WORKSHEET_NAME)
                print(f"      [INFO] Використовується аркуш: '{settings.INTERN_WORKSHEET_NAME}'")
            except gspread.WorksheetNotFound:
                print(
                    f"      [WARNING] Аркуш з назвою '{settings.INTERN_WORKSHEET_NAME}' не знайдено. Спроба взяти перший аркуш.")
                worksheet = sheet.get_worksheet(0)

            all_data = worksheet.get_all_values()
            data = all_data[1:]

        except Exception as e:
            raise ImportError(f"Помилка читання даних стажерів з Google Sheets: {e}")

        imported_count = 0
        IDX_DATE, IDX_PIN, IDX_NAME = 1, 3, 4  # Індекси: B=1, D=3, E=4

        for idx, row in enumerate(data):
            row_number = idx + 2
            if len(row) <= IDX_NAME:
                continue

            date_str = row[IDX_DATE].strip()
            pin = re.sub(r'\s+', '', row[IDX_PIN]).strip()
            full_name = row[IDX_NAME].strip()

            if not all([date_str, pin, full_name]):
                print(f"      [SKIP-MISSING] Рядок {row_number}: Дані пропущені.")
                continue

            internship_end_date = None
            try:
                excel_date_number = int(date_str)
                base_date = datetime(1899, 12, 30).date()
                internship_end_date = base_date + timedelta(days=excel_date_number)
            except ValueError:
                date_formats = ['%d.%m.%Y %H:%M:%S', '%d.%m.%Y', '%Y-%m-%d']
                for fmt in date_formats:
                    try:
                        internship_end_date = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
                if not internship_end_date:
                    print(f"      [SKIP] Невірний формат дати для ПІН {pin} (Значення: '{date_str}').")
                    continue

            existing_intern = db.query(Intern).filter(Intern.pin == pin).first()
            if existing_intern:
                existing_intern.full_name = full_name
                existing_intern.internship_end_date = internship_end_date
            else:
                new_intern = Intern(pin=pin, full_name=full_name, internship_end_date=internship_end_date)
                db.add(new_intern)
            imported_count += 1

        try:
            db.commit()
            print(f"      [Importer] Успішно імпортовано/оновлено {imported_count} стажерів.")
        except IntegrityError as e:
            db.rollback()
            raise ImportError(f"Помилка цілісності БД при імпорті стажерів: {e}")

    def run_import(self):
        """Основна функція для виконання імпорту."""
        for db in get_db():
            try:
                self.import_interns(db)
                # Тут можна додати виклик імпорту питань, якщо потрібно
                print("   [Importer] ✅ Імпорт даних з Google Sheets завершено успішно.")
            except ImportError as e:
                print(f"   [Importer] ❌ Критична помилка імпорту: {e}")
                raise
            except Exception as e:
                print(f"   [Importer] ❌ Невідома помилка під час імпорту: {e}")
                raise


def import_interns_data(SessionLocal: Callable):
    """Точка входу для запуску імпорту даних."""
    try:
        importer = GoogleSheetImporter()
        importer.run_import()
    except ImportError as e:
        raise
    except Exception as e:
        # ❗️❗️❗️ ОСЬ ГОЛОВНА ЗМІНА ДЛЯ ДІАГНОСТИКИ ❗️❗️❗️
        # Цей код надрукує повний звіт про помилку в консоль.
        print("\n--- ДЕТАЛЬНИЙ ЗВІТ ПРО ПОМИЛКУ ---")
        traceback.print_exc()
        print("---------------------------------\n")
        raise ImportError(f"Невідома помилка під час повного імпорту: {e}")