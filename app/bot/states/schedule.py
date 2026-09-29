from aiogram.fsm.state import State, StatesGroup


class ScheduleState(StatesGroup):
    choosing_day = State()
    waiting_for_time = State()
    choosing_duration = State()
    confirming = State()