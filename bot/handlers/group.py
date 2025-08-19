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
from core.config import load_config

config = load_config()
admin_ids = config.tg_bot.admin_ids

router = Router()
router.message.filter(AdminFilter(admin_ids))


@router.callback_query(F.data.startswith("read_groups_"))
async def read_groups(callback: CallbackQuery):
    """Просмотр списка групп"""
    site_id = int(parse_callback(callback.data)[2])

    # получение списка групп
    groups = await GroupService.get_groups(site_id, callback.from_user.id)

    text = (
        "📂 <b>Список групп</b>\n\n"
        "🔹 Здесь отображаются все группы, созданные для этого сайта.\n\n"
        "➡️ Перейдя в конкретную группу, вы сможете:\n"
        "   • Добавлять ссылки для парсинга.\n"
        "   • Создавать таблицы для анализа данных.\n"
        "   • Запускать парсинг прямо из группы.\n\n"
        "Выберите группу ниже 👇"
        if groups else
        "⚠️ <b>Групп пока нет</b>\n\n"
        "Создайте первую группу, чтобы начать работу:\n"
        "   • Добавляйте ссылки для парсинга.\n"
        "   • Формируйте таблицы для анализа.\n"
        "   • Запускайте парсинг в пару кликов.\n\n"
    )

    await callback.message.edit_text(
        text,
        reply_markup = groups_list_keyboard(groups, site_id, page = 1)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("groups_page_"))
async def groups_page(callback: CallbackQuery):
    """Переключение страниц списка групп"""
    _, _, site_id, page = parse_callback(callback.data)

    # получение списка групп для пагинации
    groups = await GroupService.get_groups(int(site_id), callback.from_user.id)

    await callback.message.edit_reply_markup(
        reply_markup = groups_list_keyboard(groups, int(site_id), int(page))
    )
    await callback.answer()


@router.callback_query(F.data.startswith("add_group_"))
async def add_group_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления новой группы"""
    site_id = int(parse_callback(callback.data)[2])

    # состояние добавления новой группы
    await state.update_data(site_id = site_id)
    await state.set_state(GroupStates.adding_group)

    text = (
        "🆕 <b>Создание новой группы</b>\n\n"
        "Введите название для группы, чтобы было удобно её находить в списке.\n"
        "Например: <i>«Анализ противогазов»</i> или <i>«Анализ мотоциклов»</i>.\n\n"
        "👉 Отправьте название ниже:"
    )
    await callback.message.answer(text = text)
    await callback.answer()


@router.message(GroupStates.adding_group)
async def add_group_name(message: Message, state: FSMContext):
    """Добавление названия новой группы"""
    data = await state.get_data()
    site_id = data["site_id"]

    # получение из базы Сайт по его ID
    site = await SiteService.get_site(int(site_id))

    # получение название группы из текста
    group_title = message.text

    # валидация названия группы
    if error := await GroupHandler.validate_group_title(group_title):
        await message.answer(error)
        return

    group_title = group_title.strip()
    # создание новой группы в базе данных
    await GroupService.add_group(
        site_id = site_id,
        title = group_title,
        telegram_id = message.from_user.id
    )

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

    await message.answer(f"✅ Группа '{group_title}' успешно добавлена!")
    await message.answer(
        text = text,
        reply_markup = site_actions_keyboard(site_id)
    )
    await state.clear()


@router.callback_query(F.data.startswith("delete_group_"))
async def delete_groups_menu(callback: CallbackQuery):
    """Меню удаления групп"""
    site_id = int(parse_callback(callback.data)[2])

    # получение списка групп
    groups = await GroupService.get_groups(site_id, callback.from_user.id)

    text = (
        "⚠️ Группы отсутствуют\n\n"
        "На этом сайте пока нет созданных групп, которые можно удалить.\n\n"
        "👉 Сначала добавьте хотя бы одну группу через меню «➕ Добавить группу»."
    )

    delete_text = (
        "🗑 <b>Удаление группы</b>\n\n"
        "Выберите группу, которую хотите удалить с этого сайта.\n"
        "⚠️ Удаление <b>безвозвратно</b> — вместе с ней исчезнут все связанные данные.\n\n"
        "👉 Выберите группу из списка ниже:"
    )

    if not groups:
        await callback.answer(text)
    else:
        await callback.message.edit_text(
            text = delete_text,
            reply_markup = delete_groups_keyboard(groups, site_id, page = 1)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_groups_page_"))
async def delete_groups_page(callback: CallbackQuery):
    """Переключение страниц при удалении групп"""
    _, _, site_id, page = parse_callback(callback.data)

    # получение списка групп
    groups = await GroupService.get_groups(int(site_id), callback.from_user.id)

    await callback.message.edit_reply_markup(
        reply_markup = delete_groups_keyboard(groups, int(site_id), int(page))
    )
    await callback.answer()


@router.callback_query(F.data.startswith("group_delete_"))
async def delete_group(callback: CallbackQuery):
    """Подтверждение удаления группы"""
    _, _, group_id, site_id, page = parse_callback(callback.data)

    # получение группы
    group = await GroupService.get_group(int(group_id))
    # получение количества ссылок в группе(для анализа)
    count_links = await LinkService.get_count_product_link_by_group_id(group_id = group_id)

    text = (
        f"Информация о группе:\n\n"
        f"Название: {group.title}\n"
        f"Дата создания: {group.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"Активна: {'Да' if group.is_active else 'Нет'}\n"
        f"Количество ссылок для анализа в группе: {count_links}"
    )
    text += "<b>\n\nВы уверены, что хотите удалить эту группу?</b>"

    await callback.message.edit_text(
        text,
        reply_markup = confirm_delete_group_keyboard(group.id, int(site_id), int(page))
    )
    await callback.answer()


@router.callback_query(F.data.startswith(("group_confirm_", "group_cancel_")))
async def process_delete_group_confirmation(callback: CallbackQuery):
    """Обработка подтверждения удаления группы"""
    parts = parse_callback(callback.data)
    site_id, page = int(parts[-2]), int(parts[-1])

    if callback.data.startswith("group_confirm_"):
        group_id = int(parts[2])
        await GroupService.delete_group(group_id)
        await callback.answer("✅ Группа удалена!")
    else:
        await callback.answer("❌ Удаление отменено.")

    groups = await GroupService.get_groups(site_id, callback.from_user.id)

    delete_text = (
        "🗑 <b>Удаление группы</b>\n\n"
        "Выберите группу, которую хотите удалить с этого сайта.\n"
        "⚠️ Удаление <b>безвозвратно</b> — вместе с ней исчезнут все связанные данные.\n\n"
        "👉 Выберите группу из списка ниже:"
    )

    text = (
        "✅ Все ваши группы удалены!\n\n"
        "Сейчас у вас нет активных групп.\n"
        "Вы можете создать новую группу или выбрать другое действие ниже ⬇️"
    )

    if groups:
        await callback.message.edit_text(
            delete_text,
            reply_markup = delete_groups_keyboard(groups, site_id, page)
        )
    else:

        await callback.message.edit_text(
            text,
            reply_markup = site_actions_keyboard(site_id)
        )


@router.callback_query(F.data.startswith("group_info_"))
async def group_info(callback: CallbackQuery):
    """Просмотр информации о группе"""
    _, _, group_id, site_id = parse_callback(callback.data)

    # получение группы
    group = await GroupService.get_group(int(group_id))

    # получение количества ссылок в группе(для анализа)
    count_links = await LinkService.get_count_product_link_by_group_id(group_id = group_id)

    parser_text = (
        "⏸ Остановить парсер — остановить процесс парсинга по расписанию.\n"
        if group.is_active else
        "▶️ Запустить парсер — запустить процесс парсинга по расписанию.\n"
    )

    text = (
        f"ℹ️ Информация о группе:\n\n"
        f"Название: {group.title}\n"
        f"Дата создания: {group.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"Статус: {'Активна ✅' if group.is_active else 'Неактивна ❌'}\n"
        f"Количество ссылок для анализа: {count_links}\n\n"

        "Доступные действия:\n"
        "📊 Просмотреть таблицу — посмотреть содержимое выбранной таблицы.\n"
        "📑 Просмотр последних результатов — увидеть итоговые данные последних парсеров.\n"
        "➕ Добавить таблицу — создать новую таблицу для данных (если добавить несколько раз разных таблиц,"
        " ссылки складываются в основную таблицу).\n"
        "❌ Удалить таблицу — удалить ненужную таблицу.\n"
        f"{parser_text}"
        "⏭ Принудительный запуск — запустить парсер немедленно, игнорируя расписание.\n"
        "📈 Получение анализа — получить аналитические данные по текущим таблицам.\n\n"
        "Выберите действие, которое хотите выполнить, используя кнопки ниже ⬇️"
    )

    await callback.message.edit_text(
        text,
        reply_markup = group_detail_keyboard(group.id, int(site_id), group.is_active)
    )
    await callback.answer()
