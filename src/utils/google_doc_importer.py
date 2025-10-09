import os
import re
import requests
import json
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from googleapiclient.errors import HttpError
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from ..core.config import settings
from ..database.models import Question, AnswerOption, UserAnswer  # ❗️ ДОДАНО UserAnswer
from .google_sheet_importer import ImportError

# Регулярний вираз для очищення тексту питання від нумерації типу "1. ", "2.", "Q: "
QUESTION_START_REGEX = re.compile(r'^\s*(\d+\.?\s*|Q\s*:\s*)?')

# 🎯 ФРАЗА ДЛЯ ІГНОРУВАННЯ
EXCLUDED_PHRASE = "До якого типу відноситься цей пристрій для паріння?"


class GoogleDocsImporter:
    """
    Клас для імпорту питань, варіантів відповідей та зображень з Google Docs/Drive.
    """

    def __init__(self):
        try:
            credentials_info = json.loads(settings.GOOGLE_CREDENTIALS_JSON)
        except json.JSONDecodeError:
            raise ImportError("Помилка парсингу GOOGLE_CREDENTIALS_JSON. Перевірте формат змінної у .env.")
        except AttributeError:
            raise ImportError("Змінна GOOGLE_CREDENTIALS_JSON не знайдена в налаштуваннях.")

        self.creds = Credentials.from_service_account_info(credentials_info)
        self.docs_service = build('docs', 'v1', credentials=self.creds)
        self.drive_service = build('drive', 'v3', credentials=self.creds)
        os.makedirs(settings.PHOTO_DIR, exist_ok=True)

    # ------------------- допоміжні методи -------------------

    def _is_green(self, rgb_color: dict) -> bool:
        if rgb_color:
            r, g, b = rgb_color.get('red', 0), rgb_color.get('green', 0), rgb_color.get('blue', 0)
            return g > 0.15 and g > r + 0.1 and g > b + 0.1
        return False

    def _download_image(self, file_id: str, file_extension: str = 'png') -> str | None:
        try:
            if self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(requests.Request())

            download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
            filename = f"q_{file_id}.{file_extension}"
            filepath = os.path.join(settings.PHOTO_DIR, filename)
            headers = {'Authorization': f'Bearer {self.creds.token}'}

            response = requests.get(download_url, headers=headers, stream=True)
            response.raise_for_status()

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"      [DRIVE SUCCESS] Зображення {file_id} збережено як {filename}")
            return filepath
        except Exception as e:
            print(f"      [DOWNLOAD ERROR] Невідома помилка завантаження {file_id}: {e}")
            return None

    def _extract_text_content_and_style(self, element: Any, document: Any) -> tuple[str, bool, str | None]:
        text_content, is_correct_style, image_id = "", False, None
        if 'paragraph' in element:
            for elem in element.get('paragraph').get('elements', []):
                if 'textRun' in elem:
                    text_run = elem.get('textRun', {})
                    text_content += text_run.get('content', '')
                    rgb = text_run.get('textStyle', {}).get('foregroundColor', {}).get('color', {}).get('rgbColor', {})
                    if self._is_green(rgb):
                        is_correct_style = True
                elif 'inlineObjectElement' in elem:
                    inline_obj_id = elem['inlineObjectElement']['inlineObjectId']
                    embedded_object = document.get('inlineObjects', {}).get(inline_obj_id, {}).get(
                        'inlineObjectProperties', {}).get('embeddedObject', {})
                    if 'imageProperties' in embedded_object:
                        content_uri = embedded_object['imageProperties'].get('contentUri')
                        if content_uri:
                            match = re.search(r'(?:id=|/d/)([a-zA-Z0-9_-]+)', content_uri)
                            if match:
                                image_id = match.group(1)
            text_content = text_content.replace('\xa0', ' ').strip()
        return text_content, is_correct_style, image_id

    def _save_question_to_db(self, db: Session, q_text: str, photo_path: str | None, options: list):
        try:
            current_question = Question(text=q_text, photo_url=photo_path)
            db.add(current_question)
            db.flush()
            if not any(opt['is_correct'] for opt in options):
                print(f"      [WARNING] Питання '{q_text[:50]}...' не має правильної відповіді.")
            for opt in options:
                db.add(AnswerOption(question_id=current_question.id, text=opt['text'], is_correct=opt['is_correct']))
        except Exception as e:
            print(f"      [ERROR] Помилка збереження питання '{q_text[:30]}...': {e}")

    # ------------------- основний метод імпорту -------------------

    def import_questions(self, db: Session):
        print("      [Importer] Початок імпорту питань з Google Docs...")
        try:
            document = self.docs_service.documents().get(documentId=settings.QUESTION_DOC_ID).execute()
        except HttpError as e:
            raise ImportError(f"Помилка доступу до Google Docs: {e}.")

        # ❗️❗️❗️ ОСЬ ЗМІНА ❗️❗️❗️
        # Очищення таблиць перед імпортом у правильному порядку
        try:
            # 1. Спочатку видаляємо залежні записи (відповіді користувачів)
            db.query(UserAnswer).delete(synchronize_session=False)

            # 2. Потім видаляємо основні записи (варіанти відповідей)
            db.query(AnswerOption).delete(synchronize_session=False)

            # 3. І наостанок - самі питання
            db.query(Question).delete(synchronize_session=False)

            db.commit()
            print("      [INFO] Старі результати, питання та варіанти видалено.")
        except Exception as e:
            db.rollback()
            print(f"      [WARNING] Не вдалося очистити таблиці: {e}")

        elements = document.get('body', {}).get('content', [])
        current_question_text, current_options, current_image_id = None, [], None
        question_count, is_ignoring_block = 0, False

        for element in elements:
            text_content, is_correct, element_image_id = self._extract_text_content_and_style(element, document)
            if element_image_id:
                current_image_id = element_image_id
            if not text_content:
                continue

            if text_content.endswith(':'):
                if EXCLUDED_PHRASE in text_content:
                    is_ignoring_block = True
                    current_question_text = None
                    continue
                if current_question_text and current_options:
                    photo_path = self._download_image(current_image_id) if current_image_id else None
                    self._save_question_to_db(db, current_question_text, photo_path, current_options)
                    question_count += 1
                current_question_text = QUESTION_START_REGEX.sub('', text_content).strip()
                current_options, current_image_id, is_ignoring_block = [], element_image_id, False
            elif is_ignoring_block:
                continue
            elif current_question_text and text_content.startswith('-'):
                option_text = text_content.lstrip('-').strip()
                if option_text:
                    current_options.append({'text': option_text, 'is_correct': is_correct})
            elif current_question_text:
                current_question_text = (current_question_text + " " + text_content).strip()

        if current_question_text and current_options and not is_ignoring_block:
            photo_path = self._download_image(current_image_id) if current_image_id else None
            self._save_question_to_db(db, current_question_text, photo_path, current_options)
            question_count += 1

        try:
            db.commit()
            print(f"      [Importer] Успішно імпортовано {question_count} питань.")
        except IntegrityError as e:
            db.rollback()
            raise ImportError(f"Помилка цілісності БД при імпорті питань: {e}")