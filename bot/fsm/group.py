from aiogram.fsm.state import StatesGroup, State


class GroupStates(StatesGroup):
    adding_group = State()
    deleting_group = State()
