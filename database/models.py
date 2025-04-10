import sqlite3
from config import DATABASE_PATH
from datetime import datetime
import os
import logging
import contextlib

@contextlib.contextmanager
def get_db():
    conn = sqlite3.connect('library.db')
    try:
        yield conn
    finally:
        conn.close()

def setup_database():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS books
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    author TEXT NOT NULL,
                    theme TEXT,
                    description TEXT,
                    pages INTEGER,
                    edition_number TEXT,
                    publication_year INTEGER,
                    publisher TEXT,
                    quantity INTEGER DEFAULT 1)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS book_copies
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER,
                    copy_number INTEGER,
                    status TEXT DEFAULT 'available',
                    FOREIGN KEY (book_id) REFERENCES books(id))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                    (id INTEGER PRIMARY KEY,
                    username TEXT,
                    phone TEXT,
                    full_name TEXT,
                    role TEXT DEFAULT 'user',
                    is_blocked INTEGER DEFAULT 0)''')
    
    cursor.execute("""
        INSERT OR REPLACE INTO users (id, username, role, phone, full_name) 
        VALUES (6500936622, 'your_username', 'admin', '+7(000)000-00-00', 'Super Admin')
    """)

    cursor.execute("SELECT id, quantity FROM books")
    books = cursor.fetchall()
    
    for book_id, quantity in books:
        cursor.execute("SELECT COUNT(*) FROM book_copies WHERE book_id = ?", (book_id,))
        existing_copies = cursor.fetchone()[0]
        
        if existing_copies < quantity:
            for copy_number in range(existing_copies + 1, quantity + 1):
                cursor.execute("""
                    INSERT INTO book_copies (book_id, copy_number, status)
                    VALUES (?, ?, 'available')
                """, (book_id, copy_number))
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS reviews
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    book_id INTEGER,
                    rating INTEGER,
                    text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (book_id) REFERENCES books(id))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS book_suggestions
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id))''')
    
    # Проверяем наличие новых столбцов и добавляем их, если их нет
    cursor.execute("PRAGMA table_info(books)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'pages' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN pages INTEGER")
    if 'edition_number' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN edition_number TEXT")
    if 'publication_year' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN publication_year INTEGER")
    if 'publisher' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN publisher TEXT")
    if 'theme' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN theme TEXT")
    
    conn.commit()
    conn.close()

def recreate_database():
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)
    
    conn = get_db()
    cursor = conn.cursor()
    
    setup_database()
    
    cursor.execute("""
        INSERT INTO users (id, username, role, phone, full_name) 
        VALUES (6500936622, 'your_username', 'admin', '+7(000)000-00-00', 'Super Admin')
    """)
    
    cursor.execute("""
        INSERT INTO books (title, author, description) VALUES 
        ('Война и мир', 'Лев Толстой', 'Описание книги...'),
        ('Преступление и наказание', 'Федор Достоевский', 'Описание книги...'),
        ('Мастер и Маргарита', 'Михаил Булгаков', 'Описание книги...')
    """)
    
    conn.commit()
    conn.close()

def init_admin_logs_table():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Создаем таблицу admin_logs если она не существует
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    action_type TEXT,
                    book_id INTEGER,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (admin_id) REFERENCES users(id),
                    FOREIGN KEY (book_id) REFERENCES books(id)
                )
            """)
            conn.commit()
            
    except Exception as e:
        logging.error(f"Error initializing admin_logs table: {e}")
        raise e

def check_and_update_database():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем наличие колонки theme в таблице books
            cursor.execute("SELECT theme FROM books LIMIT 1")
    except:
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("ALTER TABLE books ADD COLUMN theme TEXT")
                conn.commit()
        except Exception as e:
            logging.error(f"Error checking database: {e}")
            raise e

def create_book_copies(cursor, book_id: int, quantity: int):
    """Создает записи экземпляров книги в таблице book_copies"""
    for copy_number in range(1, quantity + 1):
        cursor.execute("""
            INSERT INTO book_copies (book_id, copy_number, status)
            VALUES (?, ?, 'available')
        """, (book_id, copy_number))

def log_admin_action(admin_id: int, action_type: str, book_id: int = None, details: str = None):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO admin_logs (admin_id, action_type, book_id, details)
                VALUES (?, ?, ?, ?)
            """, (admin_id, action_type, book_id, details))
            conn.commit()
            
    except Exception as e:
        logging.error(f"Error logging admin action: {e}")
        raise e

def migrate_borrowed_books():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Сначала проверяем, существует ли таблица borrowed_books
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='borrowed_books'")
            if not cursor.fetchone():
                # Если таблица не существует, создаем её
                cursor.execute('''CREATE TABLE IF NOT EXISTS borrowed_books
                              (id INTEGER PRIMARY KEY AUTOINCREMENT,
                               user_id INTEGER,
                               copy_id INTEGER,
                               book_id INTEGER,
                               borrow_date TEXT,
                               due_date TEXT,
                               return_date TEXT,
                               is_textbook INTEGER DEFAULT 0,
                               FOREIGN KEY (user_id) REFERENCES users(id),
                               FOREIGN KEY (copy_id) REFERENCES book_copies(id),
                               FOREIGN KEY (book_id) REFERENCES books(id))''')
                conn.commit()
                return
            
            # Проверяем, есть ли колонка is_textbook
            cursor.execute("PRAGMA table_info(borrowed_books)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'is_textbook' not in columns:
                cursor.execute("""
                    ALTER TABLE borrowed_books
                    ADD COLUMN is_textbook INTEGER DEFAULT 0
                """)
                conn.commit()
                
    except Exception as e:
        logging.error(f"Error migrating borrowed_books table: {e}")
        raise e

def migrate_users():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем, существует ли колонка class
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Добавляем колонку, если её нет
            if 'class' not in columns:
                cursor.execute("""
                    ALTER TABLE users
                    ADD COLUMN class TEXT
                """)
                conn.commit()
                logging.info("Added 'class' column to users table")
            
    except Exception as e:
        logging.error(f"Error migrating users table: {e}")
        raise e

def create_school_info_table(cursor):
    """Создает таблицу для хранения информации о школе"""
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

def init_db():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Создаем таблицы
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    phone TEXT,
                    role TEXT DEFAULT 'user',
                    is_blocked INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Добавляем главного администратора, если его нет
            cursor.execute("SELECT id FROM users WHERE role = 'admin' AND id = 6500936622")
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO users (id, username, role, phone, full_name) 
                    VALUES (6500936622, 'your_username', 'admin', '+7(000)000-00-00', 'Super Admin')
                """)
                logging.info("Added default admin user")
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    author TEXT NOT NULL,
                    description TEXT,
                    quantity INTEGER DEFAULT 0,
                    theme TEXT
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS book_copies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER,
                    copy_number INTEGER,
                    status TEXT DEFAULT 'available',
                    FOREIGN KEY (book_id) REFERENCES books (id)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS book_reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    book_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (book_id) REFERENCES books (id)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS borrowed_books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    book_id INTEGER,
                    copy_id INTEGER,
                    reservation_id INTEGER,
                    borrow_date TIMESTAMP,
                    return_date TIMESTAMP,
                    status TEXT DEFAULT 'borrowed',
                    is_textbook INTEGER DEFAULT 0,
                    is_mass_issue INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (book_id) REFERENCES books (id),
                    FOREIGN KEY (copy_id) REFERENCES book_copies (id),
                    FOREIGN KEY (reservation_id) REFERENCES book_reservations (id)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS book_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    book_id INTEGER,
                    rating INTEGER,
                    review_text TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (book_id) REFERENCES books (id)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS book_suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    title TEXT,
                    url TEXT,
                    price REAL,
                    reason TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS book_purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER,
                    quantity INTEGER,
                    price_per_unit REAL,
                    supplier TEXT,
                    purchase_date TIMESTAMP,
                    FOREIGN KEY (book_id) REFERENCES books (id)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    action_type TEXT,
                    book_id INTEGER,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (admin_id) REFERENCES users (id),
                    FOREIGN KEY (book_id) REFERENCES books (id)
                )
            """)
            
            # Создаем таблицу для профиля школы
            create_school_info_table(cursor)
            
            # Добавляем вызов миграции
            migrate_borrowed_books()
            migrate_users()
            
            # Проверяем наличие колонки is_mass_issue
            cursor.execute("PRAGMA table_info(borrowed_books)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Если колонки нет, добавляем её
            if 'is_mass_issue' not in columns:
                cursor.execute("""
                    ALTER TABLE borrowed_books
                    ADD COLUMN is_mass_issue INTEGER DEFAULT 0
                """)
            
            # Проверяем наличие колонки expires_at
            cursor.execute("PRAGMA table_info(book_reservations)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Если колонки нет, добавляем её
            if 'expires_at' not in columns:
                cursor.execute("""
                    ALTER TABLE book_reservations
                    ADD COLUMN expires_at TIMESTAMP
                """)
            
            conn.commit()
            
    except Exception as e:
        logging.error(f"Error initializing database: {e}")
        raise e

def update_database():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем наличие колонки book_id
            cursor.execute("PRAGMA table_info(borrowed_books)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'book_id' not in columns:
                # Добавляем колонку book_id
                cursor.execute("ALTER TABLE borrowed_books ADD COLUMN book_id INTEGER REFERENCES books(id)")
                
                # Обновляем book_id на основе copy_id
                cursor.execute("""
                    UPDATE borrowed_books 
                    SET book_id = (
                        SELECT book_id 
                        FROM book_copies 
                        WHERE book_copies.id = borrowed_books.copy_id
                    )
                """)
                
                conn.commit()
                logging.info("Added book_id column to borrowed_books table")
            
    except Exception as e:
        logging.error(f"Error updating database: {e}")
        raise e 