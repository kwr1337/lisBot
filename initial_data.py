from database.models import get_db, setup_database
import os

def create_database():
    if not os.path.exists('library.db'):
        setup_database()
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR IGNORE INTO users (id, username, role, phone, full_name) 
            VALUES (6500936622, 'your_username', 'admin', '+7(000)000-00-00', 'Super Admin')
        """)
        
        conn.commit()
        conn.close()
        
        print("База данных успешно создана!")
    else:
        print("База данных уже существует")

if __name__ == "__main__":
    create_database() 