from aiogram.fsm.state import StatesGroup, State
from aiogram_dialog import Dialog, Window, DialogManager
from aiogram_dialog.widgets.text import Const, Multi, Progress


class ParserStates(StatesGroup):
    progress = State()


async def get_progress(dialog_manager: DialogManager, **kwargs):
    return {"progress": dialog_manager.dialog_data.get("progress", 0)}


dialog = Dialog(
    Window(
        Multi(
            Const("⏳ Парсер выполняется, пожалуйста подождите..."),
            Progress("progress", 10),
        ),
        state = ParserStates.progress,
        getter = get_progress,
    ),
)
