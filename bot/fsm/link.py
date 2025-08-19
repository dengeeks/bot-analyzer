from aiogram.fsm.state import StatesGroup, State


class TableStates(StatesGroup):
    uploading_table = State()
