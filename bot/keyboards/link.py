from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def confirm_delete_group_links_keyboard(group_id: int, site_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"links_confirm_{group_id}_{site_id}")
    builder.button(text="❌ Отменить", callback_data=f"links_cancel_{group_id}_{site_id}")
    builder.adjust(2)
    return builder.as_markup()
