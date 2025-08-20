from aiogram.types import InlineKeyboardButton

def parse_callback(data: str) -> list[str]:
    return data.split("_")
def back_button(callback_data: str, text: str = "⬅️ Назад") -> InlineKeyboardButton:
    return InlineKeyboardButton(text = text, callback_data = callback_data)
