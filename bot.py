import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from handlers import admin, user, teacher
from database.models import check_and_update_database, init_admin_logs_table, init_db, migrate_borrowed_books
from utils.notifications import check_return_dates

# Настраиваем логирование один раз здесь
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

dp.include_router(admin.router)
dp.include_router(teacher.router)
dp.include_router(user.router)

async def main():
    try:
        # Инициализация базы данных
        init_db()
        check_and_update_database()
        init_admin_logs_table()
        migrate_borrowed_books()
        
        # Запуск проверки дат возврата
        notification_task = asyncio.create_task(check_return_dates(bot))
        
        logging.info('Бот запущен')
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f'Ошибка при запуске бота: {e}')
    finally:
        # Graceful shutdown
        await bot.session.close()
        if 'notification_task' in locals():
            notification_task.cancel()

if __name__ == "__main__":
    # Инициализируем базу данных
    init_db()
    
    # Запускаем бота
    asyncio.run(main())
