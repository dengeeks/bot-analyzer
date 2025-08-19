from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.filters.admin import AdminFilter
from bot.keyboards.site import site_actions_keyboard
from bot.services.site import SiteService
from bot.utils.callback import parse_callback
from core.config import load_config

config = load_config()
admin_ids = config.tg_bot.admin_ids

router = Router()
router.message.filter(AdminFilter(admin_ids))


# Выбор действия с сайтом
@router.callback_query(F.data.startswith("site_"))
async def site_actions(callback: CallbackQuery):
    # получение из callback site_id
    _, site_id = parse_callback(callback.data)

    # получение из базы Сайт по его ID
    site = await SiteService.get_site(site_id)

    text = (
        f"🌐 Вы работаете с сайтом <b>: {site.title}</b>\n\n"
        "📖 <b>Чтение групп</b>\n"
        "   • Посмотреть список всех групп сайта.\n"
        "   • Выбрать группу и создать в ней таблицу для анализа.\n"
        "   • Запустить парсинг прямо из выбранной группы.\n\n"
        "➕ <b>Добавление группы</b>\n"
        "   • Создать новую группу для данного сайта.\n\n"
        "❌ <b>Удаление группы</b>\n"
        "   • Удалить ненужную группу.\n\n"
        "👉 Выберите нужное действие ниже:"
    )
    await callback.message.edit_text(
        text = text,
        reply_markup = site_actions_keyboard(site_id),
    )
    await callback.answer()
