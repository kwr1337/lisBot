from aiogram.fsm.state import State, StatesGroup

class UserStates(StatesGroup):
    waiting_for_search = State()
    waiting_for_review = State()
    waiting_for_rating = State()
    waiting_for_review_text = State()
    waiting_for_book_request = State()
    waiting_for_phone = State()
    waiting_for_fullname = State()
    waiting_for_days = State()
    waiting_for_extend_days = State()
    waiting_for_book_qr = State()  # Для сканирования QR-кода книги при поиске владельца 