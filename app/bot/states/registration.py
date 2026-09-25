from aiogram.fsm.state import State, StatesGroup


class RegistrationState(StatesGroup):
    waiting_for_teacher_code = State()
    waiting_for_teacher_code_change = State()