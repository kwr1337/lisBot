import sqlite3
import os

# --- Настройки ---
# Укажите ПРАВИЛЬНЫЙ путь к вашему файлу базы данных SQLite
# Обычно он находится в той же папке, что и ваш main.py или routes.py
DATABASE_FILENAME = "library.db" 
# ----------------

# Определяем абсолютный путь к базе данных относительно текущего скрипта
script_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(script_dir, DATABASE_FILENAME)

print(f"Попытка подключения к базе данных: {db_path}")

conn = None # Инициализируем conn вне блока try
try:
    # Проверяем, существует ли файл базы данных
    if not os.path.exists(db_path):
        print(f"Ошибка: Файл базы данных '{DATABASE_FILENAME}' не найден по пути '{db_path}'.")
        print("Пожалуйста, убедитесь, что имя файла и его расположение верны.")
    else:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("Подключение к базе данных успешно.")
        
        # Выполняем команду ALTER TABLE
        print("Попытка добавить столбец 'is_textbook'...")
        cursor.execute("ALTER TABLE books ADD COLUMN is_textbook TEXT DEFAULT 'N'")
        
        # Сохраняем изменения
        conn.commit()
        print("Столбец 'is_textbook' успешно добавлен в таблицу 'books'.")

except sqlite3.Error as e:
    # Проверяем, не является ли ошибка тем, что столбец уже существует
    if "duplicate column name" in str(e).lower():
        print("Столбец 'is_textbook' уже существует в таблице 'books'. Ничего делать не нужно.")
    else:
        # Выводим другие ошибки SQLite
        print(f"Произошла ошибка SQLite при добавлении столбца: {e}")
except Exception as e:
    # Выводим любые другие неожиданные ошибки
    print(f"Произошла непредвиденная ошибка: {e}")
finally:
    # Закрываем соединение, если оно было открыто
    if conn:
        conn.close()
        print("Соединение с базой данных закрыто.") 