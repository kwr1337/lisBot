from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    waiting_for_book_title = State()
    waiting_for_book_author = State()
    waiting_for_book_description = State()
    waiting_for_notification_text = State()
    waiting_for_user_id = State()
    waiting_for_qr = State()         
    waiting_for_qr_return = State()   

class AdminManageStates(StatesGroup):
    waiting_for_new_admin_id = State()
    waiting_for_admin_action = State()
    waiting_for_admin_name = State()
    waiting_for_admin_phone = State() 