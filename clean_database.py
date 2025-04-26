import sqlite3
import logging
import os
import time
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def get_db_path():
    """Получение пути к файлу базы данных"""
    base_dir = Path(__file__).resolve().parent
    return os.path.join(base_dir, 'library.db')

def clean_database(max_retries=5, timeout=20.0):
    """Очистка всех таблиц базы данных, кроме таблицы users"""
    db_path = get_db_path()
    
    if not os.path.exists(db_path):
        logging.error(f"База данных не найдена по пути: {db_path}")
        return False
    
    # Пытаемся подключиться к базе данных несколько раз
    retry_count = 0
    conn = None
    
    while retry_count < max_retries:
        try:
            conn = sqlite3.connect(db_path, timeout=timeout)
            cursor = conn.cursor()
            
            # Отключаем внешние ключи для удаления данных
            cursor.execute("PRAGMA foreign_keys = OFF")
            
            # Проверяем, не заблокирована ли база данных
            cursor.execute("BEGIN IMMEDIATE")
            
            # Получаем список всех таблиц
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            # Очищаем все таблицы кроме 'users'
            for table in tables:
                table_name = table[0]
                if table_name != 'users' and table_name != 'sqlite_sequence':
                    logging.info(f"Очистка таблицы: {table_name}")
                    cursor.execute(f"DELETE FROM {table_name}")
            
            # Сбрасываем автоинкрементные счетчики для всех таблиц, кроме users
            cursor.execute("SELECT name FROM sqlite_sequence")
            sequences = cursor.fetchall()
            
            for seq in sequences:
                table_name = seq[0]
                if table_name != 'users':
                    cursor.execute(f"UPDATE sqlite_sequence SET seq = 0 WHERE name = '{table_name}'")
            
            # Включаем обратно внешние ключи
            cursor.execute("PRAGMA foreign_keys = ON")
            
            conn.commit()
            logging.info("База данных успешно очищена (кроме таблицы users)")
            return True
            
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                retry_count += 1
                wait_time = 2 * retry_count  # Увеличиваем время ожидания с каждой попыткой
                logging.warning(f"База данных заблокирована. Повторная попытка {retry_count}/{max_retries} через {wait_time} секунд...")
                time.sleep(wait_time)
            else:
                logging.error(f"Ошибка SQLite: {e}")
                return False
                
        except Exception as e:
            logging.error(f"Ошибка при очистке базы данных: {e}")
            return False
            
        finally:
            if conn:
                conn.close()
    
    logging.error(f"Не удалось очистить базу данных после {max_retries} попыток")
    return False

if __name__ == "__main__":
    print("Запуск очистки базы данных...")
    print("ВНИМАНИЕ: Перед выполнением этой операции рекомендуется остановить веб-сервер!")
    
    proceed = input("Продолжить? (д/н): ").lower()
    if proceed in ['д', 'y', 'yes', 'да']:
        result = clean_database()
        if result:
            print("База данных успешно очищена. Таблица users сохранена.")
        else:
            print("Произошла ошибка при очистке базы данных. Проверьте журнал для подробностей.")
    else:
        print("Операция отменена пользователем.") 