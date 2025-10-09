import asyncio
import logging
from src.core.loader import setup_system, start_bot, dp, scheduler # Потрібен dp та scheduler

# Налаштування логування (дуже корисно!)
logging.basicConfig(level=logging.INFO)


async def main():
    # 1. Налаштування системи (ініціалізація БД, підключення хендлерів, запуск планувальника)
    await setup_system()

    # 2. Запуск бота
    await start_bot() # Запуск поллінгу


if __name__ == '__main__':
    try:
        # Виконання асинхронної функції main()
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        # Додаткові кроки для коректного завершення роботи
        # 1. Зупинка планувальника
        if scheduler.running:
            scheduler.shutdown()
        # 2. Очищення сховища FSM та закриття сесій
        asyncio.run(dp.storage.close())
        asyncio.run(dp.storage.wait_closed())

        print("🛑 Бот та планувальник зупинено. Сховище закрито.")