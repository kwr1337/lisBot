from aiogram.fsm.state import State, StatesGroup

class UserStates(StatesGroup):
    waiting_for_search = State()
    waiting_for_review = State()
    waiting_for_rating = State()
    waiting_for_review_text = State()
    waiting_for_book_request = State() 