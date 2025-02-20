from aiogram.fsm.state import State, StatesGroup

class TeacherStates(StatesGroup):
    waiting_for_student_id = State()
    waiting_for_student_qr = State()
    waiting_for_student_name = State()
    waiting_for_student_phone = State() 