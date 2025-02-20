from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    waiting_for_book_title = State()
    waiting_for_book_author = State()
    waiting_for_book_description = State()
    waiting_for_notification_text = State()
    waiting_for_user_id = State()
    waiting_for_qr = State()
    waiting_for_return_qr = State()
    waiting_for_student_qr = State()  # Для сканирования QR ученика
    waiting_for_books_qr = State()    # Для сканирования QR книг
    waiting_for_return_books = State() # Для массового возврата

class AdminManageStates(StatesGroup):
    waiting_for_new_admin_id = State()
    waiting_for_admin_action = State()
    waiting_for_admin_name = State()
    waiting_for_admin_phone = State()

class AdminTeacherStates(StatesGroup):
    waiting_for_teacher_id = State()
    waiting_for_teacher_name = State()
    waiting_for_teacher_class = State()
    waiting_for_teacher_phone = State() 