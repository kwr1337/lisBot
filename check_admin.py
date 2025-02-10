from database.models import get_db

def check_admin_status(user_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if user:
        print(f"User found: {user}")
    else:
        print("User not found")
    
    conn.close()

check_admin_status(6500936622) 