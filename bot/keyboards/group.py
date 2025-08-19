from math import ceil
from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models.product_group import ProductGroup
from bot.utils.callback import back_button


def paginate(items: List, page: int, per_page: int):
    total_pages = ceil(len(items) / per_page) if items else 1
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], total_pages


def groups_list_keyboard(
        groups: List[ProductGroup], site_id: int, page: int = 1, per_page: int = 5
) -> InlineKeyboardMarkup:
    page_items, total_pages = paginate(groups, page, per_page)
    builder = InlineKeyboardBuilder()

    for g in page_items:
        builder.button(text = g.title, callback_data = f"group_info_{g.id}_{site_id}")
    builder.adjust(3)

    if page > 1:
        builder.button(text = "◀️", callback_data = f"groups_page_{site_id}_{page - 1}")
    if page < total_pages:
        builder.button(text = "▶️", callback_data = f"groups_page_{site_id}_{page + 1}")
    builder.adjust(3)

    builder.row(back_button(f"site_{site_id}"))
    return builder.as_markup()


def delete_groups_keyboard(
        groups: List[ProductGroup], site_id: int, page: int = 1, per_page: int = 5
) -> InlineKeyboardMarkup:
    page_items, total_pages = paginate(groups, page, per_page)
    builder = InlineKeyboardBuilder()

    for g in page_items:
        builder.button(text = g.title, callback_data = f"group_delete_{g.id}_{site_id}_{page}")
    builder.adjust(2)

    if page > 1:
        builder.button(text = "◀️", callback_data = f"delete_groups_page_{site_id}_{page - 1}")
    if page < total_pages:
        builder.button(text = "▶️", callback_data = f"delete_groups_page_{site_id}_{page + 1}")
    builder.adjust(2)

    builder.row(back_button(f"site_{site_id}"))
    return builder.as_markup()


def group_detail_keyboard(group_id: int, site_id: int, is_parser_active: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text = "📊 Просмотреть таблицу", callback_data = f"view_table_{group_id}_{site_id}")
    builder.button(text = "📑 Просмотр последних результатов", callback_data = f"final_table_{group_id}_{site_id}")
    builder.button(text = "➕ Добавить таблицу", callback_data = f"add_table_{group_id}_{site_id}")
    builder.button(text = "❌ Удалить таблицу", callback_data = f"delete_table_{group_id}_{site_id}")

    # Кнопки управления парсером
    if is_parser_active:
        builder.button(text = "⏸ Остановить парсер", callback_data = f"stop_parser_{group_id}_{site_id}")
    else:
        builder.button(text = "▶️ Запустить парсер", callback_data = f"start_parser_{group_id}_{site_id}")

    # Новые кнопки
    builder.button(text = "⏭ Принудительный запуск", callback_data = f"force_start_{group_id}_{site_id}")
    builder.button(text="📈 Получение анализа", callback_data=f"price_analysis_{group_id}_{site_id}")

    builder.adjust(2, 2, 2, 1, 1)
    builder.row(InlineKeyboardButton(text = "⬅️ Назад к списку групп", callback_data = f"read_groups_{site_id}"))
    return builder.as_markup()


def confirm_delete_group_keyboard(group_id: int, site_id: int, page: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text = "✅ Подтвердить", callback_data = f"group_confirm_{group_id}_{site_id}_{page}")
    builder.button(text = "❌ Отменить", callback_data = f"group_cancel_{site_id}_{page}")
    builder.adjust(2)
    return builder.as_markup()
