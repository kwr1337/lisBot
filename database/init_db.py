# Создание таблицы для хранения информации о школе
def create_school_info_table(cursor):
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS school_info (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT DEFAULT 'school',
        address TEXT,
        phone TEXT,
        email TEXT,
        website TEXT,
        director TEXT,
        description TEXT,
        logo_url TEXT
    )
    ''')

# Вызываем функцию создания таблицы школы
create_school_info_table(cursor) 