import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from handlers import admin, user
from database.models import check_and_update_database, init_admin_logs_table, init_db
from utils.notifications import check_return_dates

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Подключаем только один раз каждый роутер
dp.include_router(admin.router)  # Убрали дублирование admin_router
dp.include_router(user.router)

async def main():
    # Сначала создаем базу данных
    init_db()
    # Затем проверяем и обновляем структуру
    check_and_update_database()
    init_admin_logs_table()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    
    asyncio.create_task(check_return_dates(bot))
    
    logging.info('Бот запущен')
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
