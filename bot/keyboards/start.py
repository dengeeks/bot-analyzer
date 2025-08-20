from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def main_start_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📂 Выбрать сайт", callback_data="menu_sites")
    builder.adjust(2)
    return builder.as_markup()
