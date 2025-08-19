from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.callback import back_button


def get_sites_keyboard(sites) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in sites:
        builder.button(text=s.title, callback_data=f"site_{s.id}")
    builder.adjust(1)
    builder.row(back_button("back_to_start"))
    return builder.as_markup()


def site_actions_keyboard(site_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📖 Чтение групп", callback_data=f"read_groups_{site_id}")
    builder.button(text="➕ Добавление группы", callback_data=f"add_group_{site_id}")
    builder.button(text="❌ Удаление группы", callback_data=f"delete_group_{site_id}")
    builder.adjust(2, 1)
    builder.row(back_button("menu_sites"))
    return builder.as_markup()
