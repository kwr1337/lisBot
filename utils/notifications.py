from datetime import datetime, timedelta
from database.models import get_db
import asyncio
import logging

async def check_return_dates(bot):
    while True:  # Бесконечный цикл для периодической проверки
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                
                # Получаем книги, которые нужно вернуть через 2 дня
                two_days_later = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
                cursor.execute("""
                    SELECT bb.id, bb.user_id, b.title, bb.return_date
                    FROM borrowed_books bb
                    JOIN books b ON bb.book_id = b.id
                    JOIN users u ON bb.user_id = u.id
                    WHERE bb.return_date = ? AND bb.status = 'borrowed'
                """, (two_days_later,))
                
                to_notify = cursor.fetchall()
                
                # Отправляем уведомления
                for borrow_id, user_id, book_title, return_date in to_notify:
                    try:
                        await bot.send_message(
                            user_id,
                            f"⚠️ Напоминание!\n\n"
                            f"Книгу «{book_title}» нужно вернуть через 2 дня ({return_date})"
                        )
                    except Exception as e:
                        logging.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
                
                # Получаем просроченные книги
                cursor.execute("""
                    SELECT bb.id, bb.user_id, b.title
                    FROM borrowed_books bb
                    JOIN books b ON bb.book_id = b.id
                    WHERE bb.status = 'borrowed' 
                    AND bb.return_date < date('now')
                """)
                overdue_books = cursor.fetchall()
                
                # Отправляем уведомления о просрочке
                for borrow_id, user_id, book_title in overdue_books:
                    try:
                        await bot.send_message(
                            user_id,
                            f"🚨 ВНИМАНИЕ!\n\n"
                            f"Вы просрочили возврат книги «{book_title}»!\n"
                            f"Пожалуйста, верните книгу в библиотеку как можно скорее."
                        )
                    except Exception as e:
                        logging.error(f"Ошибка отправки уведомления о просрочке пользователю {user_id}: {e}")
                        
        except Exception as e:
            logging.error(f"Error checking return dates: {e}")
            
        # Ждем 24 часа перед следующей проверкой
        await asyncio.sleep(86400)  # 86400 секунд = 24 часа 