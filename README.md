# --- Конфігурація Telegram (ОБОВ'ЯЗКОВО) ---
BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN_HERE"

# --- Налаштування Бази Даних ---
# Приклад: postgresql+psycopg2://USER:PASSWORD@localhost:5432/intern_tester_db
DATABASE_URL="YOUR_DATABASE_URL_HERE"

# --- Налаштування Google Sheets/Drive ---
# Вміст файлу credentials.json, вставлений напряму
GOOGLE_CREDENTIALS_JSON='PASTE_YOUR_NEW_GOOGLE_SERVICE_ACCOUNT_JSON_HERE'

# ID таблиці, де знаходяться дані стажерів (Ваша Google Sheet ID)
INTERN_SHEET_ID="YOUR_GOOGLE_SHEET_ID_HERE"

# ID Google DOCS, звідки імпортуємо питання (Ваш Google Doc ID)
QUESTION_DOC_ID="YOUR_GOOGLE_DOC_ID_HERE"

# --- Налаштування Директорії ---
PHOTO_DIR="data/question_photos"

# --- Налаштування Планувальника (Опціонально) ---
# SCHEDULE_TIME="16:00:00"

# 🤖 Бот для тестування стажерів (Intern Test Bot)

Telegram-бот на Python (aiogram 3) для автоматичного тестування нових стажерів. Бот використовує PostgreSQL як базу даних, імпортує питання з Google Docs та записує результати у Google Sheets.

## 📂 Структура проекту

* `/src`: Весь вихідний код бота.
  * `/core`: Налаштування (конфіг, завантажувач, стани).
  * `/database`: Моделі SQLAlchemy та налаштування сесії.
  * `/handlers`: Обробники повідомлень (реєстрація, тестування).
  * `/services`: Бізнес-логіка (робота з Google, API).
  * `/utils`: Допоміжні функції.
* `/data`: Тека для збереження фото.
* `main.py`: Головний файл для запуску бота.
* `requirements.txt`: Список залежностей.

---

## 🏁 Як запустити проект

### 1. ⚙️ Налаштування оточення

1.  **Клонуйте репозиторій:**
    ```bash
    git clone <your-repository-url>
    cd intern_test_bot
    ```

2.  **Створіть файл `.env`:**
    Скопіюйте файл `.env.example` і перейменуйте копію на `.env`.
    ```bash
    cp .env.example .env
    ```
    Відкрийте `.env` та заповніть його вашими **(НОВИМИ!) реальними** даними (токен бота, URL бази даних, Google JSON).

3.  **Створіть та активуйте віртуальне оточення:**
    * Windows:
        ```bash
        python -m venv .venv
        .\.venv\Scripts\activate
        ```
    * macOS/Linux:
        ```bash
        python3 -m venv .venv
        source .venv/bin/activate
        ```

4.  **Встановіть залежності:**
    ```bash
    pip install -r requirements.txt
    ```

### 2. 🗄️ Налаштування Бази Даних

1.  Переконайтесь, що у вас запущений сервер PostgreSQL.
2.  Створіть базу даних, яку ви вказали у `DATABASE_URL` (наприклад, `intern_tester_db`).
3.  Бот автоматично створить всі необхідні таблиці при першому запуску (завдяки `SQLAlchemy` у `database/session.py`).

### 3. 🚀 Запустіть бота

Після виконання всіх кроків, просто запустіть головний файл:

```bash
python main.py
