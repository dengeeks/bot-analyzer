import io
import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, BufferedInputFile

from bot.database.models.product_link import ProductLink
from bot.filters.admin import AdminFilter
from bot.fsm.link import TableStates
from bot.keyboards.group import group_detail_keyboard
from bot.keyboards.link import confirm_delete_group_links_keyboard
from bot.services.group import GroupService, GroupHandler
from bot.services.link import LinkService, TableHandler
from bot.tasks.parse import parse_single_group
from bot.utils.callback import parse_callback
from bot.utils.link import _process_links, generate_price_diff_excel
from core.config import load_config

logger = logging.getLogger(__name__)

config = load_config()
admin_ids = config.tg_bot.admin_ids

router = Router()
router.message.filter(AdminFilter(admin_ids))


@router.callback_query(F.data.startswith("add_table_"))
async def add_table_start(callback: CallbackQuery, state: FSMContext):
    """Обработчик начала загрузки таблицы"""
    _, _, group_id, site_id = callback.data.split("_")

    # состояние добавления таблицы
    await state.update_data(group_id = int(group_id), site_id = int(site_id))
    await state.set_state(TableStates.uploading_table)

    text = (
        "📁 Пожалуйста, отправьте файл таблицы в формате `.xlsx` или `.csv`.\n\n"
        "⚠️ Обязательно должна быть колонка с названием <b>`Ссылка на товар`</b>.\n"
        "⚠️ Все ссылки должны начинаться с <b>`https://satu.kz/`</b>, иначе они не будут приняты и не загрузятся в парсер.\n"
        "ℹ️ Остальные колонки не обязательны — бот обработает только ссылки.\n\n"
        "Пример допустимого файла:\n"
        "Название | Ссылка на товар\n"
        "Товар 1  | https://satu.kz/...\n"
        "Товар 2  | https://satu.kz/..."
    )
    await callback.message.answer(text)
    await callback.answer()


@router.message(TableStates.uploading_table, F.document)
async def upload_table(message: Message, state: FSMContext):
    """Обработка загруженной таблицы"""
    data = await state.get_data()
    group_id = data["group_id"]
    site_id = data["site_id"]

    # получение группы
    group = await GroupService.get_group(int(group_id))

    try:
        # обработка таблицы
        file_bytes = io.BytesIO()
        await message.bot.download(message.document.file_id, destination = file_bytes)
        file_bytes.seek(0)

        df = await TableHandler.validate_and_read_file(
            file_bytes,
            message.document.file_name
        )

        if "Ссылка на товар" not in df.columns:
            raise ValueError("В таблице нет обязательной колонки 'Ссылка на товар'")

        created_count = await _process_links(df["Ссылка на товар"], group_id)

        parser_text = (
            "⏸ Остановить парсер — остановить процесс парсинга по расписанию.\n"
            if group.is_active else
            "▶️ Запустить парсер — запустить процесс парсинга по расписанию.\n"
        )

        # получение количества ссылок в группе(для анализа)
        count_links = await LinkService.get_count_product_link_by_group_id(group_id = group_id)

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

        await message.answer(
            f'✅ Успешно добавлено {created_count} ссылок',
        )
        await message.answer(
            text,
            reply_markup = group_detail_keyboard(group_id, site_id, group.is_active),

        )

    except Exception as e:
        logger.error(f"Ошибка при обработке таблицы: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        await state.clear()


@router.callback_query(F.data.startswith("view_table_"))
async def view_table(callback: CallbackQuery):
    """Генерация и отправка таблицы со ссылками"""
    _, _, group_id, site_id = callback.data.split("_")
    group_id, site_id = int(group_id), int(site_id)

    # получение группы
    group = await GroupService.get_group(group_id)
    # получение всех ссылок группы
    links = await ProductLink.filter(group_id = group_id).all()

    parser_text = (
        "⏸ Остановить парсер — остановить процесс парсинга по расписанию.\n"
        if group.is_active else
        "▶️ Запустить парсер — запустить процесс парсинга по расписанию.\n"
    )

    # получение количества ссылок в группе(для анализа)
    count_links = await LinkService.get_count_product_link_by_group_id(group_id = group_id)

    if not links:
        await callback.answer(
            "ℹ️ В этой группе пока нет ссылок для анализа.\n\n"
            "Вы можете добавить новые ссылки через кнопку «➕ Добавить таблицу» или загрузить файл с товарами."
        )
        return

    links_data = [{
        "Название компании": link.companyName,
        "Название продукта": link.productName,
        "Ссылка на товар": link.url
    } for link in links]

    excel_file = TableHandler.create_excel_with_autofit(links_data, group)

    text_table = 'Входная таблица'
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
    await callback.message.answer_document(excel_file, caption = text_table)

    await callback.message.answer(
        text,
        reply_markup = group_detail_keyboard(group.id, site_id, group.is_active)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_table_"))
async def delete_links(callback: CallbackQuery):
    """Подтверждение удаления ссылок группы"""
    _, _, group_id, site_id = parse_callback(callback.data)
    group_id, site_id = int(group_id), int(site_id)

    # получение группы
    group = await GroupService.get_group(group_id)
    # количество ссылок
    links_count = await ProductLink.filter(group_id = group_id).count()

    if not links_count:
        await callback.answer(
            "ℹ️ В этой группе пока нет ссылок, которые можно удалить.\n\n"
            "Сначала добавьте ссылки через кнопку «➕ Добавить таблицу» или загрузите файл с товарами."
        )
        return

    text = (
        f"<b>Информация о группе</b>:\n"
        f"Название: {group.title}\n"
        f"Дата создания: {group.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"Активна: {'Да' if group.is_active else 'Нет'}\n\n"
        f"<b>Информация о таблице</b>: \n"
        f"Количество ссылок: {links_count} \n\n"
        f"<b>Вы уверены, что хотите удалить все ссылки этой группы?</b>"
    )

    await callback.message.edit_text(
        text,
        reply_markup = confirm_delete_group_links_keyboard(group_id, site_id)
    )


@router.callback_query(F.data.startswith(("links_confirm_", "links_cancel_")))
async def process_delete_links_confirmation(callback: CallbackQuery):
    """Обработка подтверждения удаления ссылок"""
    parts = parse_callback(callback.data)
    group_id, site_id = int(parts[2]), int(parts[3])
    group = await GroupService.get_group(group_id)

    if callback.data.startswith("links_confirm_"):
        deleted_count = await LinkService.delete_links_by_group(group_id)
        await callback.answer(f"✅ Все ссылки ({deleted_count}) удалены!")
    else:
        await callback.answer("❌ Удаление отменено.")

    parser_text = (
        "⏸ Остановить парсер — остановить процесс парсинга по расписанию.\n"
        if group.is_active else
        "▶️ Запустить парсер — запустить процесс парсинга по расписанию.\n"
    )

    # получение количества ссылок в группе(для анализа)
    count_links = await LinkService.get_count_product_link_by_group_id(group_id = group_id)

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
        reply_markup = group_detail_keyboard(group_id, site_id, group.is_active)
    )


@router.callback_query(F.data.startswith("start_parser_"))
async def start_parser_handler(callback: CallbackQuery):
    """Обработчик запуска парсера для группы"""
    _, _, group_id, site_id = parse_callback(callback.data)
    group_id = int(group_id)

    # Обновляем статус парсера в базе данных
    group = await GroupService.update_parser_status(group_id, is_active = True)

    group = await GroupService.get_group(group_id)

    parser_text = (
        "⏸ Остановить парсер — остановить процесс парсинга по расписанию.\n"
        if group.is_active else
        "▶️ Запустить парсер — запустить процесс парсинга по расписанию.\n"
    )

    # получение количества ссылок в группе(для анализа)
    count_links = await LinkService.get_count_product_link_by_group_id(group_id = group_id)

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

    # Отправляем подтверждение и обновляем клавиатуру
    await callback.answer("✅ Парсер успешно запущен!")
    await callback.message.edit_text(
        text = text,
        reply_markup = group_detail_keyboard(
            group_id = group_id,
            site_id = int(site_id),
            is_parser_active = group.is_active
        )
    )


@router.callback_query(F.data.startswith("stop_parser_"))
async def stop_parser_handler(callback: CallbackQuery):
    """Обработчик остановки парсера для группы"""
    _, _, group_id, site_id = parse_callback(callback.data)
    group_id = int(group_id)

    # Обновляем статус парсера в базе данных
    group = await GroupService.update_parser_status(group_id, is_active = False)

    group = await GroupService.get_group(group_id)

    parser_text = (
        "⏸ Остановить парсер — остановить процесс парсинга по расписанию.\n"
        if group.is_active else
        "▶️ Запустить парсер — запустить процесс парсинга по расписанию.\n"
    )

    # получение количества ссылок в группе(для анализа)
    count_links = await LinkService.get_count_product_link_by_group_id(group_id = group_id)

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

    # Отправляем подтверждение и обновляем клавиатуру
    await callback.answer("✅ Парсер успешно запущен!")
    await callback.message.edit_text(
        text = text,
        reply_markup = group_detail_keyboard(
            group_id = group_id,
            site_id = int(site_id),
            is_parser_active = group.is_active
        )
    )


@router.callback_query(F.data.startswith("force_start_"))
async def force_start_parser(callback: CallbackQuery):
    _, _, group_id, site_id = parse_callback(callback.data)
    group = await GroupService.get_group(int(group_id))

    links_count = await ProductLink.filter(group_id = group_id).count()

    if not links_count:
        await callback.answer("В базе отсутствуют ссылки для парсинга.")
        return

    await callback.answer("⏳ Запускаю парсер...", show_alert = False)

    # Запускаем парсер для одной группы
    await parse_single_group(group_id)

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
        f"Количество ссылок для анализа: {links_count}\n\n"

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

    await callback.message.answer(f"✅ Парсер для группы {group.title} завершен")
    await callback.message.answer(
        text = text,
        reply_markup = group_detail_keyboard(
            group_id = group_id,
            site_id = int(site_id),
            is_parser_active = group.is_active
        )
    )


@router.callback_query(F.data.startswith("final_table_"))
async def view_table(callback: CallbackQuery):
    """Генерация и отправка таблицы со ссылками"""
    _, _, group_id, site_id = parse_callback(callback.data)
    group_id = int(group_id)

    group = await GroupService.get_group(group_id)
    links = await ProductLink.filter(group_id = group_id).all()

    if not links:
        await callback.answer("❌ В этой группе пока нет ссылок.")
        return

    # Проверяем, есть ли хотя бы один link с last_price != None
    has_prices = any(link.last_price is not None for link in links)

    if not has_prices:
        await callback.answer("❌ Парсинг ещё не был выполнен, данные не собраны.")
        return

    links_data = [{
        "Дата последней проверки": link.last_check.strftime("%d.%m.%Y"),
        "Название товара": link.productName,
        "Название компании": link.companyName,
        "Стоимость": link.last_price,
        "Ссылка": link.url
    } for link in links]

    excel_file = TableHandler.create_excel_with_autofit(links_data, group)

    text_table = "Выходная таблица с данными"

    parser_text = (
        "⏸ Остановить парсер — остановить процесс парсинга по расписанию.\n"
        if group.is_active else
        "▶️ Запустить парсер — запустить процесс парсинга по расписанию.\n"
    )

    links_count = await ProductLink.filter(group_id = group_id).count()

    text = (
        f"ℹ️ Информация о группе:\n\n"
        f"Название: {group.title}\n"
        f"Дата создания: {group.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"Статус: {'Активна ✅' if group.is_active else 'Неактивна ❌'}\n"
        f"Количество ссылок для анализа: {links_count}\n\n"

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

    await callback.message.answer_document(excel_file, caption = text_table)
    await callback.message.answer(
        text,
        reply_markup = group_detail_keyboard(group.id, site_id, group.is_active)
    )


@router.callback_query(F.data.startswith("price_analysis_"))
async def price_analysis(callback: CallbackQuery):
    _, _, group_id, site_id = parse_callback(callback.data)
    group_id = int(group_id)
    site_id = int(site_id)
    group = await GroupService.get_group(group_id)

    parser_text = (
        "⏸ Остановить парсер — остановить процесс парсинга по расписанию.\n"
        if group.is_active else
        "▶️ Запустить парсер — запустить процесс парсинга по расписанию.\n"
    )

    links_count = await ProductLink.filter(group_id = group_id).count()

    text = (
        f"ℹ️ Информация о группе:\n\n"
        f"Название: {group.title}\n"
        f"Дата создания: {group.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"Статус: {'Активна ✅' if group.is_active else 'Неактивна ❌'}\n"
        f"Количество ссылок для анализа: {links_count}\n\n"

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

    excel_file = await generate_price_diff_excel(group_id)
    if not excel_file:
        await callback.answer("❌ Нет данных для анализа (нет цен).", show_alert = True)
        return

    await callback.message.answer_document(
        document = BufferedInputFile(excel_file.getvalue(), filename = f"Анализ_группы_{group.title}.xlsx"),
        caption = f"📊 Анализ цен группы {group_id}"
    )
    await callback.message.answer(
        text = text,
        reply_markup = group_detail_keyboard(
            group_id = group_id,
            site_id = int(site_id),
            is_parser_active = group.is_active
        )
    )
    await callback.answer()
