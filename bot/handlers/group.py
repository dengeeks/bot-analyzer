import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot.filters.admin import AdminFilter
from bot.fsm.group import GroupStates
from bot.keyboards.group import (
    groups_list_keyboard,
    delete_groups_keyboard,
    group_detail_keyboard,
    confirm_delete_group_keyboard,
)
from bot.keyboards.site import site_actions_keyboard
from bot.services.group import GroupService, GroupHandler
from bot.services.link import LinkService
from bot.services.site import SiteService
from bot.utils.callback import parse_callback
from bot.utils.group import _get_group_info_text
from core.config import load_config

logger = logging.getLogger(__name__)

config = load_config()
admin_ids = config.tg_bot.admin_ids

router = Router()
router.message.filter(AdminFilter(admin_ids))


class GroupTextTemplates:
    """Класс для хранения текстовых шаблонов групп"""

    GROUPS_LIST_TEXT = (
        "📂 <b>Список групп</b>\n\n"
        "🔹 Здесь отображаются все группы, созданные для этого сайта.\n\n"
        "➡️ Перейдя в конкретную группу, вы сможете:\n"
        "   • Добавлять ссылки для парсинга.\n"
        "   • Создавать таблицы для анализа данных.\n"
        "   • Запускать парсинг прямо из группы.\n\n"
        "Выберите группу ниже 👇"
    )

    NO_GROUPS_TEXT = (
        "⚠️ <b>Групп пока нет</b>\n\n"
        "Создайте первую группу, чтобы начать работу:\n"
        "   • Добавляйте ссылки для парсинга.\n"
        "   • Формируйте таблицы для анализа.\n"
        "   • Запускайте парсинг в пару кликов.\n\n"
    )

    ADD_GROUP_START_TEXT = (
        "🆕 <b>Создание новой группы</b>\n\n"
        "Введите название для группы, чтобы было удобно её находить в списке.\n"
        "Например: <i>«Анализ противогазов»</i> или <i>«Анализ мотоциклов»</i>.\n\n"
        "👉 Отправьте название ниже:"
    )

    DELETE_GROUPS_TEXT = (
        "🗑 <b>Удаление группы</b>\n\n"
        "Выберите группу, которую хотите удалить с этого сайта.\n"
        "⚠️ Удаление <b>безвозвратно</b> — вместе с ней исчезнут все связанные данные.\n\n"
        "👉 Выберите группу из списка ниже:"
    )

    NO_GROUPS_DELETE_TEXT = (
        "⚠️ Группы отсутствуют\n\n"
        "На этом сайте пока нет созданных групп, которые можно удалить.\n\n"
        "👉 Сначала добавьте хотя бы одну группу через меню «➕ Добавить группу»."
    )

    ALL_GROUPS_DELETED_TEXT = (
        "✅ Все ваши группы удалены!\n\n"
        "Сейчас у вас нет активных групп.\n"
        "Вы можете создать новую группу или выбрать другое действие ниже ⬇️"
    )

    @staticmethod
    def get_site_actions_text(site_title: str) -> str:
        """Генерирует текст для действий с сайтом"""
        return (
            f"🌐 Вы работаете с сайтом <b>{site_title}</b>\n\n"
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


async def _handle_group_operation_error(callback: CallbackQuery, operation_name: str, error: Exception) -> None:
    """Обработчик ошибок для операций с группами"""
    logger.error(f"Ошибка в {operation_name}: {error}")
    await callback.answer("❌ Произошла ошибка при обработке запроса")


@router.callback_query(F.data.startswith("read_groups_"))
async def read_groups(callback: CallbackQuery):
    """Просмотр списка групп"""
    try:
        _, _, site_id = parse_callback(callback.data)
        site_id = int(site_id)
        groups = await GroupService.get_groups(site_id, callback.from_user.id)

        text = GroupTextTemplates.GROUPS_LIST_TEXT if groups else GroupTextTemplates.NO_GROUPS_TEXT

        await callback.message.edit_text(
            text,
            reply_markup = groups_list_keyboard(groups, site_id, page = 1)
        )
        await callback.answer()

    except Exception as e:
        await _handle_group_operation_error(callback, "read_groups", e)


@router.callback_query(F.data.startswith("groups_page_"))
async def groups_page(callback: CallbackQuery):
    """Переключение страниц списка групп"""
    try:
        _, _, site_id, page = parse_callback(callback.data)
        site_id = int(site_id)
        page = int(page)
        groups = await GroupService.get_groups(site_id, callback.from_user.id)

        await callback.message.edit_reply_markup(
            reply_markup = groups_list_keyboard(groups, site_id, page)
        )
        await callback.answer()

    except Exception as e:
        await _handle_group_operation_error(callback, "groups_page", e)


@router.callback_query(F.data.startswith("add_group_"))
async def add_group_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления новой группы"""
    try:
        _, _, site_id = parse_callback(callback.data)
        site_id = int(site_id)

        await state.update_data(site_id = site_id)
        await state.set_state(GroupStates.adding_group)

        await callback.message.answer(text = GroupTextTemplates.ADD_GROUP_START_TEXT)
        await callback.answer()

    except Exception as e:
        await _handle_group_operation_error(callback, "add_group_start", e)


@router.message(GroupStates.adding_group)
async def add_group_name(message: Message, state: FSMContext):
    """Добавление названия новой группы"""
    try:
        data = await state.get_data()
        site_id = int(data["site_id"])
        site = await SiteService.get_site(site_id)
        group_title = message.text.strip()

        if error := await GroupHandler.validate_group_title(group_title):
            await message.answer(error)
            return

        await GroupService.add_group(
            site_id = site_id,
            title = group_title,
            telegram_id = message.from_user.id
        )

        site_actions_text = GroupTextTemplates.get_site_actions_text(site.title)

        await message.answer(f"✅ Группа '{group_title}' успешно добавлена!")
        await message.answer(
            text = site_actions_text,
            reply_markup = site_actions_keyboard(site_id)
        )

    except Exception as e:
        logger.error(f"Ошибка в add_group_name: {e}")
        await message.answer("❌ Произошла ошибка при создании группы")
    finally:
        await state.clear()


@router.callback_query(F.data.startswith("delete_group_"))
async def delete_groups_menu(callback: CallbackQuery):
    """Меню удаления групп"""
    try:
        _, _, site_id = parse_callback(callback.data)
        site_id = int(site_id)
        groups = await GroupService.get_groups(site_id, callback.from_user.id)

        if not groups:
            await callback.answer(GroupTextTemplates.NO_GROUPS_DELETE_TEXT)
        else:
            await callback.message.edit_text(
                text = GroupTextTemplates.DELETE_GROUPS_TEXT,
                reply_markup = delete_groups_keyboard(groups, site_id, page = 1)
            )
        await callback.answer()

    except Exception as e:
        await _handle_group_operation_error(callback, "delete_groups_menu", e)


@router.callback_query(F.data.startswith("delete_groups_page_"))
async def delete_groups_page(callback: CallbackQuery):
    """Переключение страниц при удалении групп"""
    try:
        await callback.answer()

        _, _, _, site_id, page = parse_callback(callback.data)
        site_id = int(site_id)
        page = int(page)
        groups = await GroupService.get_groups(site_id, callback.from_user.id)

        await callback.message.edit_reply_markup(
            reply_markup = delete_groups_keyboard(groups, site_id, page)
        )

    except Exception as e:
        await _handle_group_operation_error(callback, "delete_groups_page", e)


@router.callback_query(F.data.startswith("group_delete_"))
async def delete_group(callback: CallbackQuery):
    """Подтверждение удаления группы"""
    try:
        _, _, group_id, site_id, page = parse_callback(callback.data)
        group_id = int(group_id)
        site_id = int(site_id)
        page = int(page)

        group = await GroupService.get_group(group_id)
        count_links = await LinkService.get_count_product_link_by_group_id(group_id = group_id)

        confirmation_text = (
            f"Информация о группе:\n\n"
            f"Название: {group.title}\n"
            f"Дата создания: {group.created_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"Активна: {'Да' if group.is_active else 'Нет'}\n"
            f"Количество ссылок для анализа в группе: {count_links}"
            f"<b>\n\nВы уверены, что хотите удалить эту группу?</b>"
        )

        await callback.message.edit_text(
            confirmation_text,
            reply_markup = confirm_delete_group_keyboard(group.id, site_id, page)
        )
        await callback.answer()

    except Exception as e:
        await _handle_group_operation_error(callback, "delete_group", e)


@router.callback_query(F.data.startswith(("group_confirm_", "group_cancel_")))
async def process_delete_group_confirmation(callback: CallbackQuery):
    """Обработка подтверждения удаления группы"""
    try:
        _, _, group_id, site_id, page = parse_callback(callback.data)
        group_id = int(group_id)
        site_id = int(site_id)
        page = int(page)

        if callback.data.startswith("group_confirm_"):
            await GroupService.delete_group(group_id)
            await callback.answer("✅ Группа удалена!")
        else:
            await callback.answer("❌ Удаление отменено.")

        groups = await GroupService.get_groups(site_id, callback.from_user.id)

        if groups:
            await callback.message.edit_text(
                GroupTextTemplates.DELETE_GROUPS_TEXT,
                reply_markup = delete_groups_keyboard(groups, site_id, page)
            )
        else:
            await callback.message.edit_text(
                GroupTextTemplates.ALL_GROUPS_DELETED_TEXT,
                reply_markup = site_actions_keyboard(site_id)
            )

    except Exception as e:
        await _handle_group_operation_error(callback, "process_delete_group_confirmation", e)


@router.callback_query(F.data.startswith("group_info_"))
async def group_info(callback: CallbackQuery):
    """Просмотр информации о группе"""
    try:
        _, _, group_id, site_id = parse_callback(callback.data)
        group_id = int(group_id)
        site_id = int(site_id)

        group_info_text = await _get_group_info_text(group_id)
        group = await GroupService.get_group(group_id)

        await callback.message.edit_text(
            group_info_text,
            reply_markup = group_detail_keyboard(group.id, site_id, group.is_active)
        )
        await callback.answer()

    except Exception as e:
        await _handle_group_operation_error(callback, "group_info", e)
